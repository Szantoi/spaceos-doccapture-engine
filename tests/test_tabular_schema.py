"""A fejléc-illesztés szabályai.

A tesztek nem azt mérik, hogy a `bind()` visszaad-e valamit, hanem hogy
**elbukik-e ott, ahol el kell**. A csábító viselkedés minden itt mért esetben az
lenne, hogy „valamit csak válasszunk" — és épp az a veszélyes, mert működik.
"""

from __future__ import annotations

import unittest

from doccapture.core.errors import (
    AmbiguousHeaderError,
    ConfigurationError,
    SchemaMismatchError,
    SourceUnreadableError,
)
from doccapture.core.tabular import (
    ColumnSpec,
    ColumnType,
    TableSchema,
    TabularOptions,
    normalize_header,
    split_header_unit,
)


def _schema(*specs: ColumnSpec, identity: tuple[str, ...] = ()) -> TableSchema:
    return TableSchema(columns=specs, identity_keys=identity)


class BindingTests(unittest.TestCase):
    def test_a_fejlec_NEVE_szerint_kot_nem_pozicio_szerint(self) -> None:
        """A prototípus beégetett oszlop-indexet használt (`ws.cell(r, 2)`).

        Ez a teszt azt méri, hogy egy **beszúrt** oszlop nem rontja el a
        betöltést — pedig épp ez volt a prototípus legcsendesebb hibája.
        """
        schema = _schema(
            ColumnSpec("kod", ("Kód",)),
            ColumnSpec("megnevezes", ("Megnevezés",)),
        )
        binding = schema.bind(["Kód", "ÚJ OSZLOP", "Megnevezés"])

        self.assertEqual(binding.by_key("kod").index, 0)
        self.assertEqual(binding.by_key("megnevezes").index, 2)

    def test_tobb_elfogadott_fejlec_valtozat(self) -> None:
        """Ugyanazt a mezőt minden rendszer máshogy hívja — a lista NŐ."""
        schema = _schema(ColumnSpec("kod", ("Kód", "Cikkszám", "Azonosító")))
        for header in ("Kód", "Cikkszám", "Azonosító"):
            with self.subTest(header=header):
                self.assertEqual(schema.bind([header]).by_key("kod").index, 0)

    def test_az_illesztetlen_fejlec_NEM_vesz_el(self) -> None:
        """Nem hiba — de ha épp elgépelt fejléc miatt nem illeszkedett, CSAK itt látszik."""
        schema = _schema(ColumnSpec("kod", ("Kód",)))
        binding = schema.bind(["Kód", "Menyiség", "  "])

        self.assertEqual(binding.unmatched_headers, ((1, "Menyiség"),))

    def test_a_nem_kotelezo_hianyzo_oszlop_kimondva_jelenik_meg(self) -> None:
        schema = _schema(
            ColumnSpec("kod", ("Kód",)),
            ColumnSpec("egyseg", ("Mértékegység",)),
        )
        binding = schema.bind(["Kód"])

        self.assertEqual(binding.missing_optional_keys, ("egyseg",))
        self.assertIsNone(binding.by_key("egyseg"))


class FailureTests(unittest.TestCase):
    """Ahol el KELL bukni. Mindhárom esetben működne a „válassz valamit" út."""

    def test_kotelezo_oszlop_hianya_a_FORRAST_hibaztatja(self) -> None:
        schema = _schema(ColumnSpec("kod", ("Kód",), required=True))
        with self.assertRaises(SchemaMismatchError) as ctx:
            schema.bind(["Megnevezés"])
        self.assertIn("kod", str(ctx.exception))
        # A hibafajta is szerzodes: a hivo ebbol tudja, a FAJLT kell megnezni.
        self.assertIsInstance(ctx.exception, SourceUnreadableError)

    def test_ket_illeszkedo_oszlop_KETERTELMU_es_elbukik(self) -> None:
        """Nem az elsőt választjuk. Az működne — és hónapokig nem derülne ki,
        hogy a rossz oszlopból tölt."""
        schema = _schema(ColumnSpec("mennyiseg", ("Mennyiség",)))
        with self.assertRaises(AmbiguousHeaderError):
            schema.bind(["Mennyiség", "mennyiség"])

    def test_egy_oszlop_nem_lehet_ket_kulon_mezo(self) -> None:
        schema = _schema(
            ColumnSpec("a", ("Érték",)),
            ColumnSpec("b", ("Érték",)),
        )
        with self.assertRaises(AmbiguousHeaderError):
            schema.bind(["Érték"])

    def test_a_ketertelmuseg_a_semamismatch_alfajtaja(self) -> None:
        """A hívó egyben is elkaphatja mindkettőt — de szét is tudja választani."""
        self.assertTrue(issubclass(AmbiguousHeaderError, SchemaMismatchError))


class SchemaDefinitionTests(unittest.TestCase):
    """A SÉMA hibája a MI hibánk — ezért `ConfigurationError`, nem forrás-hiba.

    A szétválasztás nem stílus: az egyiket mi javítjuk, a másikat az ügyfél.
    """

    def test_ures_kulcs(self) -> None:
        with self.assertRaises(ConfigurationError):
            ColumnSpec("", ("Kód",))

    def test_fejlec_nelkuli_oszlop_soha_nem_illeszkedne(self) -> None:
        with self.assertRaises(ConfigurationError):
            ColumnSpec("kod", ())

    def test_ismetlodo_belso_kulcs(self) -> None:
        with self.assertRaises(ConfigurationError):
            _schema(ColumnSpec("kod", ("A",)), ColumnSpec("kod", ("B",)))

    def test_nem_letezo_kulcsra_hivatkozo_azonosito_szabaly(self) -> None:
        """Enélkül a sor-üresség szabálya CSENDBEN soha nem teljesülne."""
        with self.assertRaises(ConfigurationError):
            _schema(ColumnSpec("kod", ("Kód",)), identity=("nincs_ilyen",))

    def test_ures_sema(self) -> None:
        with self.assertRaises(ConfigurationError):
            TableSchema(columns=())

    def test_a_semadefinicio_hibaja_NEM_forrashiba(self) -> None:
        """Ha ez a kettő összemosódna, a hívó a fájlt keresné a saját hibája helyett."""
        with self.assertRaises(ConfigurationError) as ctx:
            ColumnSpec("", ("Kód",))
        self.assertNotIsInstance(ctx.exception, SchemaMismatchError)


class SerializationTests(unittest.TestCase):
    """A séma ADAT: ha kódban állna, minden új ügyfél kódmódosítást igényelne."""

    def test_koroda_megorzi_a_sema_minden_elemet(self) -> None:
        original = _schema(
            ColumnSpec("kod", ("Kód", "Cikkszám"), ColumnType.TEXT, True, "azonosito"),
            ColumnSpec("db", ("Mennyiség",), ColumnType.INTEGER),
            identity=("kod",),
        )
        restored = TableSchema.from_dict(original.to_dict())

        self.assertEqual(restored, original)

    def test_ismeretlen_oszlop_tipus_INDULASKOR_bukik(self) -> None:
        with self.assertRaises(ConfigurationError):
            TableSchema.from_dict(
                {"columns": [{"key": "a", "headers": ["A"], "column_type": "nincs_ilyen"}]}
            )

    def test_a_sztringkent_megadott_fejlec_lista_kimondott_hiba(self) -> None:
        """Gyakori elírás. Csendben KARAKTEREKRE esne szét, és a séma három
        egykarakteres fejlécet fogadna el — ami soha nem illeszkedne."""
        with self.assertRaises(ConfigurationError) as ctx:
            TableSchema.from_dict({"columns": [{"key": "a", "headers": "Kód"}]})
        self.assertIn("listát vár", str(ctx.exception))

    def test_ures_sema_leiras(self) -> None:
        with self.assertRaises(ConfigurationError):
            TableSchema.from_dict({"columns": []})


class NormalizationTests(unittest.TestCase):
    def test_a_korulvagas_es_a_szokoz_osszevonas_MINDIG_megtortenik(self) -> None:
        """A másolt fejlécekben rendszeresen van törhetetlen szóköz és soremelés."""
        options = TabularOptions()
        self.assertEqual(
            normalize_header("  Nettó \n  érték ", options),
            normalize_header("Nettó érték", options),
        )

    def test_az_ekezet_hajtogatas_alapbol_KI_van_kapcsolva(self) -> None:
        """Miért: az összevonás két különböző fejlécet egybe olvaszthat, és
        abból kétértelműség lesz — a betöltés elbukik ott, ahol addig működött."""
        self.assertFalse(TabularOptions().header_match_strip_accents)
        options = TabularOptions()
        self.assertNotEqual(
            normalize_header("szám", options), normalize_header("szam", options)
        )

    def test_az_ekezet_hajtogatas_bekapcsolhato(self) -> None:
        options = TabularOptions(header_match_strip_accents=True)
        self.assertEqual(
            normalize_header("Mennyiség", options), normalize_header("Mennyiseg", options)
        )

    def test_a_bekapcsolt_hajtogatas_ELOALLITHATJA_a_ketertelmuseget(self) -> None:
        """Ezt nem elrejtjük, hanem MEGMÉRJÜK — ez a kapcsoló ára."""
        schema = _schema(ColumnSpec("szam", ("szám",)))
        options = TabularOptions(header_match_strip_accents=True)
        schema.bind(["szám"], options)  # ekezettel egyedul: rendben
        with self.assertRaises(AmbiguousHeaderError):
            schema.bind(["szám", "szam"], options)


class UnitInHeaderTests(unittest.TestCase):
    """M15: a mértékegységet megőrizzük, de nem tesszük fel."""

    def test_a_zarojeles_egyseg_levalik_es_megmarad(self) -> None:
        self.assertEqual(split_header_unit("Hossz (mm)"), ("Hossz", "mm"))
        self.assertEqual(split_header_unit("Terület [m2]"), ("Terület", "m2"))

    def test_egyseg_nelkuli_fejlec_valtozatlan(self) -> None:
        self.assertEqual(split_header_unit("Megnevezés"), ("Megnevezés", ""))

    def test_a_KOZEPEN_allo_zarojel_nem_egyseg(self) -> None:
        """Ha annak vennénk, a CÍMKÉT rontanánk el — és akkor a fejléc nem illeszkedne."""
        self.assertEqual(
            split_header_unit("Nettó (áfa nélkül) érték"),
            ("Nettó (áfa nélkül) érték", ""),
        )

    def test_a_teljesen_zarojelezett_fejlec_nem_egyseg(self) -> None:
        self.assertEqual(split_header_unit("(megjegyzés)"), ("(megjegyzés)", ""))

    def test_az_egyseges_es_az_egyseg_nelkuli_fejlec_UGYANARRA_illik(self) -> None:
        """Különben egy mértékegység feltüntetése elrontaná a betöltést."""
        schema = _schema(ColumnSpec("mennyiseg", ("Mennyiség",)))
        binding = schema.bind(["Mennyiség (m2)"])
        self.assertEqual(binding.by_key("mennyiseg").unit, "m2")
        self.assertEqual(binding.units, {"mennyiseg": "m2"})


if __name__ == "__main__":
    unittest.main()
