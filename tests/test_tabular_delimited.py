"""Az elválasztott szöveges adapter — függőség nélküli út.

Amit itt mérünk, az nem a `csv` modul (azt nem a mi dolgunk tesztelni), hanem
hogy az adapter **jól adja a cellákat**, a bizonyíték a **fájlban lévő** helyre
mutat, és minden kihagyás **megszámolva** jelenik meg.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.models import Confidence
from doccapture.core.tabular import ColumnSpec, ColumnType, TableSchema, TabularOptions
from doccapture.infrastructure.tabular.delimited import DelimitedTabularReader

SCHEMA = TableSchema(
    columns=(
        ColumnSpec("kod", ("Kód",), ColumnType.TEXT, required=True),
        ColumnSpec("megnevezes", ("Megnevezés",), ColumnType.TEXT),
        ColumnSpec("mennyiseg", ("Mennyiség",), ColumnType.NUMBER),
    ),
    identity_keys=("kod",),
)


class _Fixture:
    """Egy eldobható forrás-mappa egyetlen fájllal."""

    def __init__(self, content: str, name: str = "lista.csv", encoding: str = "utf-8") -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.name = name
        (self.root / name).write_text(content, encoding=encoding)

    def reader(self, **options) -> DelimitedTabularReader:
        config = CaptureConfig(
            input_root=str(self.root), tabular=TabularOptions(**options)
        )
        return DelimitedTabularReader(config)

    def close(self) -> None:
        self._tmp.cleanup()


class ReadingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _Fixture(
            "Kód;Megnevezés;Mennyiség\n"
            "A-1;Első tétel;12,5\n"
            "A-2;Második tétel;3\n"
        )
        self.addCleanup(self.fixture.close)

    def test_a_sorok_a_BELSO_kulcsokkal_jonnek(self) -> None:
        """Nem a fejléc szövegével: egy átnevezett oszlop különben az egész
        láncot elrontaná."""
        result = self.fixture.reader(decimal_separator=",").read(self.fixture.name, SCHEMA)

        self.assertEqual(len(result.rows), 2)
        self.assertEqual(sorted(result.rows[0]), ["kod", "megnevezes", "mennyiseg"])
        self.assertEqual(result.rows[0]["kod"].value, "A-1")
        self.assertEqual(result.rows[0]["mennyiseg"].value, 12.5)
        self.assertEqual(result.rows[1]["mennyiseg"].value, 3.0)

    def test_a_bizonyitek_a_FAJLBAN_levo_helyre_mutat(self) -> None:
        """A sorszám a fájl szerinti, nem a saját számlálónk — különben egy
        kihagyott sor után a bizonyíték rossz helyre mutat, és épp
        ellenőrzéskor derül ki, hogy nem stimmel."""
        result = self.fixture.reader(decimal_separator=",").read(self.fixture.name, SCHEMA)

        evidence = result.rows[0]["kod"].evidence
        self.assertEqual(evidence.relative_path, "lista.csv")
        self.assertTrue(evidence.content_hash.startswith("sha256:"))
        self.assertEqual(evidence.locator, "R2C1")  # 1. adatsor = a fajl 2. sora
        self.assertEqual(result.rows[1]["kod"].evidence.locator, "R3C1")

    def test_minden_cella_UGYANARRA_a_tartalom_hashre_hivatkozik(self) -> None:
        """A hash-elés fájlonként egyszer fut. Ha cellánként futna, egy 5000
        soros fájlt tízezerszer olvasnánk végig."""
        result = self.fixture.reader(decimal_separator=",").read(self.fixture.name, SCHEMA)
        hashes = {
            item.evidence.content_hash for row in result.rows for item in row.values()
        }
        self.assertEqual(len(hashes), 1)

    def test_a_ketertelmu_szam_a_SORBAN_is_hiany(self) -> None:
        """Tizedesjel megadása nélkül a `12,5` kétértelmű lenne… de nem az:
        egy számjegy van utána. Amit mérünk: a beállítás nélkül is helyes
        eredmény jön, tehát az alapértelmezés nem használhatatlan."""
        result = self.fixture.reader().read(self.fixture.name, SCHEMA)
        self.assertEqual(result.rows[0]["mennyiseg"].value, 12.5)


class HeaderPositionTests(unittest.TestCase):
    def test_a_fejlec_nem_feltetlenul_az_elso_sor(self) -> None:
        """A prototípus ezt beégette. Valós fájlokban van előtte címsor."""
        fixture = _Fixture(
            "Beszállítói árlista 2026\n"
            "\n"
            "Kód;Megnevezés;Mennyiség\n"
            "A-1;Tétel;1\n"
        )
        self.addCleanup(fixture.close)

        result = fixture.reader(header_row=3).read(fixture.name, SCHEMA)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["kod"].evidence.locator, "R4C1")

    def test_a_fejlec_alatti_egyseg_sor_kihagyhato(self) -> None:
        fixture = _Fixture(
            "Kód;Megnevezés;Mennyiség\n"
            ";;db\n"
            "A-1;Tétel;1\n"
        )
        self.addCleanup(fixture.close)

        result = fixture.reader(data_starts_after_header=1).read(fixture.name, SCHEMA)
        self.assertEqual(len(result.rows), 1)
        self.assertEqual(result.rows[0]["kod"].value, "A-1")

    def test_ha_a_fejlec_sor_nem_letezik_kimondott_hiba(self) -> None:
        fixture = _Fixture("Kód;Megnevezés\n")
        self.addCleanup(fixture.close)

        with self.assertRaises(SourceUnreadableError) as ctx:
            fixture.reader(header_row=9).read(fixture.name, SCHEMA)
        self.assertIn("9", str(ctx.exception))


class SkippedRowTests(unittest.TestCase):
    """A prototípus itt `if desc:`-cel némán dobott sorokat."""

    def test_az_ures_sorok_szama_MERT_es_kimondott(self) -> None:
        fixture = _Fixture(
            "Kód;Megnevezés;Mennyiség\n"
            "A-1;Tétel;1\n"
            ";;\n"
            ";Megjegyzés a lap alján;\n"
            "A-2;Tétel;2\n"
        )
        self.addCleanup(fixture.close)

        result = fixture.reader().read(fixture.name, SCHEMA)

        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.skipped_blank_rows, 2)
        self.assertTrue(
            any("2 sor üresként kihagyva" in note for note in result.diagnostics),
            result.diagnostics,
        )

    def test_az_EMBERI_KITOLTESRE_jelolt_azonosito_oszlop_nem_uriti_ki_a_sort(self) -> None:
        """A néma sor-eltűnés második esete (M7).

        Ha a sor-üresség az értelmezett értékből dolgozna, egy emberi kitöltésre
        jelölt azonosító oszlop MINDEN sort üresnek mutatna — vagyis a betöltés
        **nulla sorral** térne vissza, és úgy néz ki, mint egy üres fájl.
        """
        schema = TableSchema(
            columns=(
                ColumnSpec(
                    "kod", ("Kód",), ColumnType.TEXT, required=True, field_type="azonosito"
                ),
                ColumnSpec("megnevezes", ("Megnevezés",), ColumnType.TEXT),
            ),
            identity_keys=("kod",),
        )
        fixture = _Fixture("Kód;Megnevezés\nA-1;Tétel\nA-2;Másik\n")
        self.addCleanup(fixture.close)

        config = CaptureConfig(
            input_root=str(fixture.root), human_only_field_types=["azonosito"]
        )
        result = DelimitedTabularReader(config).read(fixture.name, schema)

        self.assertEqual(len(result.rows), 2, "a sorok eltuntek — nema adatvesztes")
        self.assertEqual(result.skipped_blank_rows, 0)
        self.assertIs(result.rows[0]["kod"].confidence, Confidence.MISSING)
        self.assertIn("emberi kitöltésre", result.rows[0]["kod"].note)
        # A tobbi oszlop viszont NORMALISAN olvasodik.
        self.assertEqual(result.rows[0]["megnevezes"].value, "Tétel")

    def test_azonosito_oszlop_nelkul_MINDEN_sor_adatsor(self) -> None:
        """Nem találjuk ki, mi az „üres": ha nincs azonosító szabály, nem dobunk."""
        schema = TableSchema(columns=SCHEMA.columns)  # identity_keys nelkul
        fixture = _Fixture("Kód;Megnevezés;Mennyiség\nA-1;T;1\n;;\n")
        self.addCleanup(fixture.close)

        result = fixture.reader().read(fixture.name, schema)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.skipped_blank_rows, 0)


class TruncationTests(unittest.TestCase):
    def test_a_sor_korlat_elerese_KIMONDOTT_nem_nema(self) -> None:
        """Egy néma csonkolás pontosan úgy néz ki, mint egy hiánytalan betöltés."""
        fixture = _Fixture(
            "Kód;Megnevezés;Mennyiség\n" + "".join(f"A-{i};T;1\n" for i in range(10))
        )
        self.addCleanup(fixture.close)

        result = fixture.reader(max_rows=3).read(fixture.name, SCHEMA)

        self.assertEqual(len(result.rows), 3)
        self.assertTrue(result.truncated)
        self.assertTrue(any("sor-korlát" in note for note in result.diagnostics))

    def test_korlat_alatt_nincs_csonkolas_jelzes(self) -> None:
        """A másik irány: egy mindig-igaz jelző ugyanolyan haszontalan."""
        fixture = _Fixture("Kód;Megnevezés;Mennyiség\nA-1;T;1\n")
        self.addCleanup(fixture.close)

        result = fixture.reader(max_rows=100).read(fixture.name, SCHEMA)
        self.assertFalse(result.truncated)


class DelimiterAndEncodingTests(unittest.TestCase):
    def test_az_elvalaszto_felismerese_mukodik_vesszore_es_pontosvesszore(self) -> None:
        for delimiter in (";", ",", "\t"):
            with self.subTest(delimiter=delimiter):
                fixture = _Fixture(
                    delimiter.join(["Kód", "Megnevezés", "Mennyiség"])
                    + "\n"
                    + delimiter.join(["A-1", "Tétel", "1"])
                    + "\n"
                )
                self.addCleanup(fixture.close)
                result = fixture.reader().read(fixture.name, SCHEMA)
                self.assertEqual(result.rows[0]["kod"].value, "A-1")

    def test_a_cimsor_a_fejlec_FOLOTT_nem_zavarja_a_felismerest(self) -> None:
        """⚠ Ezt egy bukó teszt hozta elő. A szabványkönyvtár felismerője
        sor-konzisztenciát igényel, tehát egy cím-sor a fejléc fölött
        megbuktatta — pedig az a sor nem is táblázat-sor. Az új szabály a
        **fejléc-sorból** dolgozik, ezért a preambulum nem érdekli."""
        fixture = _Fixture(
            "Beszállítói árlista 2026 — nincs benne elválasztó\n"
            "\n"
            "Kód;Megnevezés;Mennyiség\n"
            "A-1;Tétel;1\n"
        )
        self.addCleanup(fixture.close)

        result = fixture.reader(header_row=3).read(fixture.name, SCHEMA)
        self.assertEqual(result.rows[0]["kod"].value, "A-1")

    def test_a_holtverseny_ELBUKIK_nem_tippel(self) -> None:
        """Két jelölt ugyanannyi előfordulással valóban eldönthetetlen."""
        fixture = _Fixture("Kód;Megnevezés,Mennyiség\nA-1;T,1\n")
        self.addCleanup(fixture.close)

        with self.assertRaises(SourceUnreadableError) as ctx:
            fixture.reader().read(fixture.name, SCHEMA)
        self.assertIn("eldönthetetlen", str(ctx.exception))

    def test_a_dominans_elvalaszto_nyer_de_a_masikat_KIMONDJUK(self) -> None:
        """A `Nettó, bruttó` fejlécben van vessző is. A döntés megmagyarázható,
        de ha mégis rossz, CSAK a diagnosztikából derül ki."""
        schema = TableSchema(
            columns=(
                ColumnSpec("kod", ("Kód",), ColumnType.TEXT, required=True),
                ColumnSpec("ertek", ("Nettó, bruttó",), ColumnType.TEXT),
            )
        )
        fixture = _Fixture("Kód;Nettó, bruttó;Egyéb\nA-1;100;x\n")
        self.addCleanup(fixture.close)

        result = fixture.reader().read(fixture.name, schema)
        self.assertEqual(result.rows[0]["kod"].value, "A-1")
        self.assertTrue(
            any("szerepel még" in note for note in result.diagnostics), result.diagnostics
        )

    def test_a_szokoz_NEM_lehet_elvalaszto_jelolt(self) -> None:
        """Ez a lelet gyökere: a felismerő a szóközt választotta, és a fejléc
        szavakra esett szét. A configban ez ma nem is beállítható."""
        from doccapture.core.errors import ConfigurationError

        with self.assertRaises(ConfigurationError) as ctx:
            TabularOptions(delimiter_candidates=[";", " "]).validate()
        self.assertIn("térköz", str(ctx.exception))

    def test_a_tabulator_KIVETEL_a_terkoz_tilalom_alol(self) -> None:
        """A másik irány: egy túl szigorú szabály a tabulátorral tagolt
        fájlokat zárná ki, pedig azok teljesen szabályosak."""
        TabularOptions(delimiter_candidates=["\t"]).validate()

    def test_felismerhetetlen_elvalaszto_KIMONDOTT_hiba_nem_tipp(self) -> None:
        """Rossz elválasztóval a teljes fájl egyetlen oszlop lenne, és a hiba a
        séma-illesztésnél jelenne meg — értelmezhetetlen üzenettel."""
        fixture = _Fixture("csak egy hosszu sor mindenfele elvalaszto nelkul\n")
        self.addCleanup(fixture.close)

        with self.assertRaises(SourceUnreadableError) as ctx:
            fixture.reader().read(fixture.name, SCHEMA)
        self.assertIn("elválasztó", str(ctx.exception))

    def test_a_megadott_elvalaszto_felulirja_a_felismerest(self) -> None:
        fixture = _Fixture("Kód|Megnevezés|Mennyiség\nA-1|Tétel|1\n")
        self.addCleanup(fixture.close)

        result = fixture.reader(delimiter="|").read(fixture.name, SCHEMA)
        self.assertEqual(result.rows[0]["kod"].value, "A-1")

    def test_a_BOM_os_fajl_elso_fejlece_nem_serul(self) -> None:
        """BOM nélkül az első fejléc `\\ufeffKód` lenne, és CSENDBEN nem illeszkedne."""
        fixture = _Fixture("Kód;Megnevezés;Mennyiség\nA-1;T;1\n", encoding="utf-8-sig")
        self.addCleanup(fixture.close)

        result = fixture.reader().read(fixture.name, SCHEMA)
        self.assertEqual(result.rows[0]["kod"].value, "A-1")

    def test_dekodolhatatlan_fajl_kimondott_hiba(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        Path(tmp.name, "lista.csv").write_bytes(b"K\xf3d;N\xe9v\n\xff\xfe;x\n")

        config = CaptureConfig(input_root=tmp.name)
        with self.assertRaises(SourceUnreadableError) as ctx:
            DelimitedTabularReader(config).read("lista.csv", SCHEMA)
        self.assertIn("kódolás", str(ctx.exception))

    def test_ures_fajl_kimondott_hiba(self) -> None:
        fixture = _Fixture("")
        self.addCleanup(fixture.close)

        with self.assertRaises(SourceUnreadableError):
            fixture.reader().read(fixture.name, SCHEMA)


class ReadOnlySourceTests(unittest.TestCase):
    """M10: a forrás csak olvasható — nincs létrehozás, átnevezés, törlés, másolás.

    Ezt NEM állítjuk, hanem **megmérjük**: a mappa teljes tartalmát
    összehasonlítjuk a betöltés előtt és után.
    """

    def test_a_betoltes_semmit_nem_valtoztat_a_forras_mappaban(self) -> None:
        from doccapture.infrastructure.evidence import content_hash

        fixture = _Fixture("Kód;Megnevezés;Mennyiség\nA-1;T;1\n")
        self.addCleanup(fixture.close)

        def snapshot() -> dict[str, tuple[int, int, str]]:
            return {
                path.name: (
                    path.stat().st_size,
                    path.stat().st_mtime_ns,
                    content_hash(path),
                )
                for path in sorted(fixture.root.rglob("*"))
                if path.is_file()
            }

        before = snapshot()
        fixture.reader().read(fixture.name, SCHEMA)
        after = snapshot()

        self.assertEqual(before, after)
        self.assertEqual(len(before), 1, "a mero maga hozott letre fajlt?")


class PathSafetyTests(unittest.TestCase):
    def test_a_gyokerbol_kilepo_ut_elbukik(self) -> None:
        fixture = _Fixture("Kód\nA-1\n")
        self.addCleanup(fixture.close)

        from doccapture.core.errors import ConfigurationError

        with self.assertRaises((ConfigurationError, SourceUnreadableError)):
            fixture.reader().read("../lista.csv", SCHEMA)

    def test_az_abszolut_ut_elbukik(self) -> None:
        fixture = _Fixture("Kód\nA-1\n")
        self.addCleanup(fixture.close)

        from doccapture.core.errors import ConfigurationError

        with self.assertRaises(ConfigurationError):
            fixture.reader().read(str(fixture.root / fixture.name), SCHEMA)


class MissingValueTests(unittest.TestCase):
    def test_a_hianyzo_cella_HIANY_nem_kivetel(self) -> None:
        fixture = _Fixture("Kód;Megnevezés;Mennyiség\nA-1;;\n")
        self.addCleanup(fixture.close)

        result = fixture.reader().read(fixture.name, SCHEMA)
        self.assertIs(result.rows[0]["megnevezes"].confidence, Confidence.MISSING)
        self.assertTrue(result.needs_human)

    def test_a_rovid_sor_nem_szall_el(self) -> None:
        """Valós exportokban a záró üres cellák lemaradnak."""
        fixture = _Fixture("Kód;Megnevezés;Mennyiség\nA-1\n")
        self.addCleanup(fixture.close)

        result = fixture.reader().read(fixture.name, SCHEMA)
        self.assertEqual(result.rows[0]["kod"].value, "A-1")
        self.assertIs(result.rows[0]["mennyiseg"].confidence, Confidence.MISSING)


if __name__ == "__main__":
    unittest.main()
