"""Az érték-értelmezés szabályai — ahol a bizonytalanság ADAT lesz.

A legfontosabb tesztek itt azt mérik, hogy **hol NEM adunk értéket**. Egy
értelmező, ami mindig ad valamit, pontosan olyan, mint egy mindig zöld teszt.
"""

from __future__ import annotations

import datetime as dt
import unittest

from doccapture.core.models import Confidence, SourceEvidence
from doccapture.core.tabular import ColumnSpec, ColumnType, TabularOptions, interpret_cell
from doccapture.core.tabular.options import _UNAMBIGUOUS_GROUP_SEPARATORS
from doccapture.core.tabular.values import UnreadableCell, parse_number

TEXT = ColumnSpec("t", ("T",), ColumnType.TEXT)
NUMBER = ColumnSpec("n", ("N",), ColumnType.NUMBER)
INTEGER = ColumnSpec("i", ("I",), ColumnType.INTEGER)
DATE = ColumnSpec("d", ("D",), ColumnType.DATE)
BOOLEAN = ColumnSpec("b", ("B",), ColumnType.BOOLEAN)


class NumberAmbiguityTests(unittest.TestCase):
    """A `"1,234"` lehet 1234 és lehet 1.234 — és NINCS locale-mentes szabály rá."""

    def test_a_ketertelmu_szam_HIANY_nem_tipp(self) -> None:
        for text in ("1,234", "12,345", "123,456", "1.234"):
            with self.subTest(text=text):
                value, problem = parse_number(text)
                self.assertIsNone(value)
                self.assertIn("kétértelmű", problem)

    def test_megadott_tizedesjel_ELTUNTETI_a_ketertelmuseget(self) -> None:
        vesszo = TabularOptions(decimal_separator=",")
        self.assertEqual(parse_number("1,234", vesszo), (1.234, ""))
        # Ugyanaz a szoveg, mas beallitas -> mas ertek. Ezert nem tippelunk.
        pont = TabularOptions(decimal_separator=".")
        self.assertEqual(parse_number("1,234", pont), (1234.0, ""))

    def test_mindket_jel_eseten_az_UTOLSO_a_tizedesjel(self) -> None:
        """Univerzális: nincs írásrendszer, ahol a csoport-jel a tizedesjel után áll."""
        self.assertEqual(parse_number("1.234,56"), (1234.56, ""))
        self.assertEqual(parse_number("1,234.56"), (1234.56, ""))
        self.assertEqual(parse_number("1.234.567,89"), (1234567.89, ""))

    def test_tobbszori_elofordulas_csoport_jel(self) -> None:
        self.assertEqual(parse_number("1.234.567"), (1234567.0, ""))
        self.assertEqual(parse_number("1,234,567"), (1234567.0, ""))

    def test_nem_harom_szamjegy_utana_tizedesjel(self) -> None:
        self.assertEqual(parse_number("12,5"), (12.5, ""))
        self.assertEqual(parse_number("1234.56"), (1234.56, ""))
        # Negy jegyu egesz resz kizarja az ervenyes csoportositast.
        self.assertEqual(parse_number("1234.567"), (1234.567, ""))

    def test_elojel_es_egyszeru_egesz(self) -> None:
        self.assertEqual(parse_number("42"), (42.0, ""))
        self.assertEqual(parse_number("-42"), (-42.0, ""))
        self.assertEqual(parse_number("+42"), (42.0, ""))
        self.assertEqual(parse_number("-1.234,5"), (-1234.5, ""))

    def test_nem_szam_alaku_ertek(self) -> None:
        for text in ("kb. 5", "12%", "N/A", "1 234 Ft"):
            with self.subTest(text=text):
                value, problem = parse_number(text)
                self.assertIsNone(value)
                self.assertTrue(problem)


class GroupSeparatorTests(unittest.TestCase):
    def test_a_szokoz_fajtak_csoport_jelnek_szamitanak(self) -> None:
        self.assertEqual(parse_number("1 234 567"), (1234567.0, ""))
        self.assertEqual(parse_number("1 234 567"), (1234567.0, ""))
        self.assertEqual(parse_number("1 234"), (1234.0, ""))
        self.assertEqual(parse_number("1'234'567"), (1234567.0, ""))

    def test_a_csoport_jel_alapertelmezes_KODPONTJAI_pontosak(self) -> None:
        """Az egyetlen ok, amiért ez teszt: a törhetetlen szóközök a forrásban
        megkülönböztethetetlenek a közönséges szóköztől, tehát egy szerkesztő
        vagy egy másolás csendben kicserélhetné őket — és a csoport-jel
        eltűnése semmin nem bukna el."""
        self.assertEqual(
            [ord(ch) for ch in _UNAMBIGUOUS_GROUP_SEPARATORS],
            [0x20, 0xA0, 0x202F, 0x2009, 0x27],
        )

    def test_a_tizedesjel_es_a_csoport_jel_nem_lehet_ugyanaz(self) -> None:
        """Különben MINDEN szám kétértelmű lenne — csendben."""
        from doccapture.core.errors import ConfigurationError

        with self.assertRaises(ConfigurationError):
            TabularOptions(decimal_separator=" ").validate()


class IntegerTests(unittest.TestCase):
    def test_egesz_ertek_megbizhato(self) -> None:
        result = interpret_cell("42", INTEGER)
        self.assertEqual(result.value, 42)
        self.assertIs(result.confidence, Confidence.CONFIRMED)
        self.assertIsInstance(result.value, int)

    def test_tort_szam_egesz_oszlopban_JELOLVE_marad(self) -> None:
        """Nem kerekítünk: a kerekítés IRÁNYA üzleti döntés, nem olvasási kérdés.
        És nem is dobjuk el — az értéket megtartjuk, hogy legyen mit megnézni."""
        result = interpret_cell("12,5", INTEGER, TabularOptions(decimal_separator=","))
        self.assertEqual(result.value, 12.5)
        self.assertIs(result.confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("kerekít", result.note)


class TextTests(unittest.TestCase):
    """A táblázatos forrás NEM automatikusan megbízható."""

    def test_a_tudomanyos_alak_JELZI_hogy_a_forras_romlott(self) -> None:
        """Egy hosszú azonosító tudományos alakban tárolódik, és az eredeti
        számjegyek VÉGLEGESEN elvesznek. Itt nem az olvasás bizonytalan."""
        result = interpret_cell(1.2345678901234567e20, TEXT)
        self.assertIs(result.confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("tudományos", result.note)

    def test_a_2_53_es_1e16_KOZOTTI_RES_is_jelolve_van(self) -> None:
        """⚠ Ezt a tesztet egy SAJÁT bukó teszt hozta elő, és a lelet a
        detektorról szólt, nem a kódról.

        Az első változat csak azt vizsgálta, hogy a `repr` tudományos alakú-e.
        A `repr` viszont **csak 1e16 fölött** vált tudományos alakra, miközben a
        lebegőpontos tárolás **már 2**53 fölött** pontatlan. A kettő között van
        egy sáv, ahol a számjegyek MÁR elvesztek, de az `e`-vizsgálat még nem
        fog — vagyis a legveszélyesebb eset csúszott volna át csendben.
        """
        # 2**53 + 1: lebegopontosan mar nem abrazolhato pontosan, de a repr-je
        # NEM tudomanyos alaku -- pont a resben van.
        raw = float(2**53 + 1)
        self.assertNotIn("e", repr(raw), "a resbeli eset elment volna e-vizsgalattal")

        result = interpret_cell(raw, TEXT)
        self.assertIs(result.confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("nem pontos", result.note)

    def test_a_res_alatti_egesz_MAS_indokot_kap(self) -> None:
        """A két eset nem ugyanaz: itt a szám pontos, csak a `str()` alakja
        rossz kulcs. Ha egy indokot adnánk mindkettőre, az ember nem tudná,
        hogy pótolni kell-e a forrásból."""
        result = interpret_cell(1.23456789e15, TEXT)
        self.assertIs(result.confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("vezető nullákat", result.note)
        self.assertNotIn("nem pontos", result.note)

    def test_a_tort_resz_nelkuli_szam_szoveg_oszlopban_jelolve(self) -> None:
        """A `str(123.0)` `"123.0"`-t adna — egy cikkszámnál az rossz kulcs."""
        result = interpret_cell(123.0, TEXT)
        self.assertEqual(result.value, "123")
        self.assertIs(result.confidence, Confidence.NEEDS_REVIEW)

    def test_a_sima_szoveg_megbizhato_es_korulvagott(self) -> None:
        result = interpret_cell("  Megnevezés  ", TEXT)
        self.assertEqual(result.value, "Megnevezés")
        self.assertIs(result.confidence, Confidence.CONFIRMED)


class DateTests(unittest.TestCase):
    def test_a_natív_datum_atmegy(self) -> None:
        self.assertEqual(interpret_cell(dt.date(2026, 7, 30), DATE).value, dt.date(2026, 7, 30))
        self.assertEqual(
            interpret_cell(dt.datetime(2026, 7, 30, 12, 0), DATE).value, dt.date(2026, 7, 30)
        )

    def test_az_ISO_alak_alapbol_mukodik(self) -> None:
        """Az ISO-8601 nem locale, hanem szabvány — ezért az egyetlen alapérték."""
        self.assertEqual(interpret_cell("2026-07-30", DATE).value, dt.date(2026, 7, 30))

    def test_a_ketertelmu_sorrend_NEM_talalgatas_targya(self) -> None:
        """A nap/hónap tévedése a hónap első 12 napján HELYES eredményt ad,
        ezért sokáig rejtve marad. Inkább hiány."""
        result = interpret_cell("03/04/2026", DATE)
        self.assertIsNone(result.value)
        self.assertIs(result.confidence, Confidence.MISSING)

    def test_kimondott_alak_beallithato(self) -> None:
        options = TabularOptions(date_formats=["%d.%m.%Y"])
        self.assertEqual(interpret_cell("30.07.2026", DATE, options).value, dt.date(2026, 7, 30))


class BooleanTests(unittest.TestCase):
    def test_nativ_es_szoveges_alak(self) -> None:
        self.assertIs(interpret_cell(True, BOOLEAN).value, True)
        self.assertIs(interpret_cell("TRUE", BOOLEAN).value, True)
        self.assertIs(interpret_cell("false", BOOLEAN).value, False)

    def test_ismeretlen_alak_hiany(self) -> None:
        result = interpret_cell("igen", BOOLEAN)
        self.assertIsNone(result.value)
        self.assertIs(result.confidence, Confidence.MISSING)

    def test_sajat_szoveges_alakok_beallithatok(self) -> None:
        options = TabularOptions(true_values=["igen", "x"], false_values=["nem"])
        self.assertIs(interpret_cell("x", BOOLEAN, options).value, True)
        self.assertIs(interpret_cell("nem", BOOLEAN, options).value, False)


class TypeConfusionTests(unittest.TestCase):
    """Amiket a Python típusrendszere csendben összekeverne."""

    def test_a_logikai_ertek_NEM_szam(self) -> None:
        """A `bool` a Pythonban `int`: a `True` észrevétlenül 1-re változna."""
        result = interpret_cell(True, NUMBER)
        self.assertIsNone(result.value)
        self.assertIs(result.confidence, Confidence.MISSING)

    def test_a_nulla_es_a_hamis_NEM_ures(self) -> None:
        """A `if not value:` mindkettőt üresnek vennné — az adatvesztés."""
        self.assertEqual(interpret_cell(0, NUMBER).value, 0.0)
        self.assertIs(interpret_cell(0, NUMBER).confidence, Confidence.CONFIRMED)
        self.assertIs(interpret_cell(False, BOOLEAN).value, False)
        self.assertIs(interpret_cell(False, BOOLEAN).confidence, Confidence.CONFIRMED)


class MissingAndUnreadableTests(unittest.TestCase):
    def test_az_ures_cella_HIANY_nem_kivetel(self) -> None:
        for raw in (None, "", "   "):
            with self.subTest(raw=raw):
                result = interpret_cell(raw, TEXT)
                self.assertIs(result.confidence, Confidence.MISSING)
                self.assertEqual(result.note, "üres cella")

    def test_az_OLVASHATATLAN_cella_NEM_ugyanaz_mint_az_ures(self) -> None:
        """Ez a szelet legdrágább leletje. Ha összemosódnának, a sor akár üres
        sorként kiesne — néma adatvesztés."""
        result = interpret_cell(UnreadableCell("képlet gyorsítótár nélkül"), TEXT)
        self.assertIs(result.confidence, Confidence.MISSING)
        self.assertEqual(result.note, "képlet gyorsítótár nélkül")
        self.assertNotEqual(result.note, "üres cella")

    def test_az_olvashatatlansag_minden_oszlop_tipuson_atmegy(self) -> None:
        for spec in (TEXT, NUMBER, INTEGER, DATE, BOOLEAN):
            with self.subTest(spec=spec.column_type):
                result = interpret_cell(UnreadableCell("ok"), spec)
                self.assertEqual(result.note, "ok")


class HumanOnlyTests(unittest.TestCase):
    """M7: amit tudottan rosszul olvasunk, azt ne olvassuk gépileg."""

    def test_az_emberi_kitoltesre_jelolt_mezo_HIANYT_ad_akkor_is_ha_van_ertek(self) -> None:
        spec = ColumnSpec("vonalkod", ("Vonalkód",), ColumnType.TEXT, field_type="azonosito")
        result = interpret_cell("1234567890123456", spec, human_only=True)

        self.assertIsNone(result.value)
        self.assertIs(result.confidence, Confidence.MISSING)
        self.assertIn("emberi kitöltésre", result.note)
        self.assertIn("azonosito", result.note)

    def test_kikapcsolva_normalisan_olvas(self) -> None:
        spec = ColumnSpec("vonalkod", ("Vonalkód",), ColumnType.TEXT, field_type="azonosito")
        self.assertEqual(interpret_cell("1234", spec, human_only=False).value, "1234")


class EvidenceTests(unittest.TestCase):
    def test_a_bizonyitek_atkerul_minden_kimenetre(self) -> None:
        """Egy érték bizonyíték nélkül visszakövethetetlen — és a hiány is adat,
        tehát annak IS kell bizonyíték."""
        evidence = SourceEvidence("lista.csv", "sha256:abc", "R2C1")
        self.assertIs(interpret_cell("x", TEXT, evidence=evidence).evidence, evidence)
        self.assertIs(interpret_cell(None, TEXT, evidence=evidence).evidence, evidence)
        self.assertIs(
            interpret_cell("kb. 5", NUMBER, evidence=evidence).evidence, evidence
        )


if __name__ == "__main__":
    unittest.main()
