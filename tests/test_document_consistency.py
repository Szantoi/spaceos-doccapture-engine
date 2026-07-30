"""Az önellenőrző számtan — M3 (jelöl, nem javít) és M4 (kevésbé érzékeny út).

A két legfontosabb teszt itt:

- `test_a_bomlo_egyenloseget_JELOLI_nem_javitja` — a csendes javítás lenne a
  legdrágább hiba: az érték „helyes" lenne, és senki nem tudná, hogy nyúltunk hozzá;
- `test_a_szarmaztatott_ertek_SOHA_nem_CONFIRMED` — egy származtatott érték, ami
  megkülönböztethetetlen a leolvasottól, csendes tévedés.
"""

from __future__ import annotations

import unittest

from doccapture.core.documents import ConsistencyRule, Operation, apply_rules
from doccapture.core.errors import ConfigurationError
from doccapture.core.models import Confidence, Extracted, SourceEvidence

SZORZAT = ConsistencyRule(
    name="összes idő = ciklusidő × darabszám",
    left="total",
    operands=("cycle", "qty"),
    operation=Operation.PRODUCT,
)
OSSZEG = ConsistencyRule(
    name="végösszeg = adóalap + adó",
    left="gross",
    operands=("net", "tax"),
    operation=Operation.SUM,
)


def _ok(value):
    return Extracted(value, Confidence.CONFIRMED, SourceEvidence("irat.txt", "sha256:a"))


def _missing(note="üres"):
    return Extracted(None, Confidence.MISSING, SourceEvidence("irat.txt", "sha256:a"), note)


class VerificationTests(unittest.TestCase):
    """M3 — a redundancia ingyen ellenőrzés."""

    def test_a_stimmelo_egyenloseg_nem_valtoztat_semmit(self) -> None:
        fields = {"total": _ok(20.0), "cycle": _ok(2.0), "qty": _ok(10.0)}
        result, outcomes = apply_rules(fields, (SZORZAT,), 0.01)

        self.assertEqual(outcomes[0].status, "ok")
        self.assertIs(result["total"].confidence, Confidence.CONFIRMED)
        self.assertEqual(result["total"].value, 20.0)

    def test_a_bomlo_egyenloseget_JELOLI_nem_javitja(self) -> None:
        """A csendes javítás lenne a legdrágább hiba: az érték „helyes" lenne, és
        senki nem tudná, hogy nyúltunk hozzá."""
        fields = {"total": _ok(25.0), "cycle": _ok(2.0), "qty": _ok(10.0)}
        result, outcomes = apply_rules(fields, (SZORZAT,), 0.01)

        self.assertTrue(outcomes[0].is_violation)
        self.assertEqual(result["total"].value, 25.0, "a leolvasott ertek MEGMARADT")
        self.assertIs(result["total"].confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("NEM javítottuk", result["total"].note)

    def test_a_diagnosztika_MEGNEVEZI_melyik_egyenloseg_bomlott(self) -> None:
        """Egy „valami nem stimmel" használhatatlan. A hibának visszafejthetőnek
        kell lennie abból, MELYIK egyenlőség bomlott el."""
        fields = {"total": _ok(25.0), "cycle": _ok(2.0), "qty": _ok(10.0)}
        _, outcomes = apply_rules(fields, (SZORZAT,), 0.01)

        self.assertIn("összes idő", outcomes[0].rule_name)
        self.assertIn("cycle × qty", outcomes[0].detail)
        self.assertIn("eltérés 5", outcomes[0].detail)

    def test_a_bomlas_MINDEN_erintett_mezot_megjelol(self) -> None:
        """Nem tudjuk, melyik oldal a hibás — ezért mindkettőt jelöljük.
        Ha csak a bal oldalt jelölnénk, az operandusokat helyesnek hinné a fogyasztó."""
        fields = {"total": _ok(25.0), "cycle": _ok(2.0), "qty": _ok(10.0)}
        result, _ = apply_rules(fields, (SZORZAT,), 0.01)

        for kulcs in ("total", "cycle", "qty"):
            with self.subTest(kulcs=kulcs):
                self.assertIs(result[kulcs].confidence, Confidence.NEEDS_REVIEW)

    def test_a_TURES_szabaly_szintu_lehet(self) -> None:
        """Egy pénz-egyenlőség kerekítési tűrése más, mint egy idő-összegé."""
        szabaly = ConsistencyRule(
            name="kerekítés-toleráns", left="gross", operands=("net", "tax"),
            operation=Operation.SUM, tolerance=1.0,
        )
        fields = {"gross": _ok(127.5), "net": _ok(100.0), "tax": _ok(27.0)}
        _, outcomes = apply_rules(fields, (szabaly,), 0.01)
        self.assertEqual(outcomes[0].status, "ok", "a szabaly-szintu tures nem ervenyesult")


class DerivationTests(unittest.TestCase):
    """M4 — a hibára legkevésbé érzékeny bemenetet válaszd."""

    def test_a_hianyzo_BAL_oldal_szarmaztathato(self) -> None:
        fields = {"total": _missing(), "cycle": _ok(2.0), "qty": _ok(10.0)}
        result, outcomes = apply_rules(fields, (SZORZAT,), 0.01)

        self.assertEqual(outcomes[0].status, "származtatva")
        self.assertEqual(result["total"].value, 20.0)

    def test_a_hianyzo_OPERANDUS_visszaszamolhato(self) -> None:
        """Ez a lényeg: ha a darabszám olvasása törékeny (kézírás), de az összes idő
        és a ciklusidő biztos, akkor a darabszámot AZOKBÓL számoljuk."""
        fields = {"total": _ok(20.0), "cycle": _ok(2.0), "qty": _missing("kézírás")}
        result, outcomes = apply_rules(fields, (SZORZAT,), 0.01)

        self.assertEqual(outcomes[0].status, "származtatva")
        self.assertEqual(result["qty"].value, 10.0)
        self.assertIn("M4", result["qty"].note)

    def test_a_szarmaztatott_ertek_SOHA_nem_CONFIRMED(self) -> None:
        """Egy származtatott érték, ami megkülönböztethetetlen a leolvasottól,
        csendes tévedés: a fogyasztó azt hinné, ott volt a papíron."""
        for fields in (
            {"total": _missing(), "cycle": _ok(2.0), "qty": _ok(10.0)},
            {"total": _ok(20.0), "cycle": _ok(2.0), "qty": _missing()},
        ):
            with self.subTest(fields=sorted(fields)):
                result, _ = apply_rules(fields, (SZORZAT,), 0.01)
                szarmaztatott = [
                    item for item in result.values()
                    if item.note and "származtatva" in item.note or
                       item.note and "visszaszámolva" in item.note
                ]
                self.assertTrue(szarmaztatott)
                for item in szarmaztatott:
                    self.assertIs(item.confidence, Confidence.NEEDS_REVIEW)

    def test_az_ELOZO_szabaly_szarmaztatasa_a_kovetkezo_bemenete(self) -> None:
        """Egy iraton a végösszegből visszaszámolt adóalap egy másik egyenlőség
        operandusa lehet. Ez szándékos, ezért mérjük."""
        elso = ConsistencyRule("adóalap a végösszegből", "gross", ("net", "tax"), Operation.SUM)
        masodik = ConsistencyRule("tétel = adóalap × 1", "line", ("net", "factor"), Operation.PRODUCT)
        fields = {
            "gross": _ok(127.0), "net": _missing(), "tax": _ok(27.0),
            "line": _missing(), "factor": _ok(1.0),
        }
        result, outcomes = apply_rules(fields, (elso, masodik), 0.01)

        self.assertEqual(result["net"].value, 100.0)
        self.assertEqual(result["line"].value, 100.0, "a szarmaztatott net nem jutott tovabb")
        self.assertEqual([o.status for o in outcomes], ["származtatva", "származtatva"])

    def test_a_szarmaztatas_KIKAPCSOLHATO(self) -> None:
        szabaly = ConsistencyRule("csak ellenőrzés", "total", ("cycle", "qty"), derive=False)
        fields = {"total": _missing(), "cycle": _ok(2.0), "qty": _ok(10.0)}
        result, outcomes = apply_rules(fields, (szabaly,), 0.01)

        self.assertEqual(outcomes[0].status, "nem futott")
        self.assertIsNone(result["total"].value)

    def test_a_nullaval_osztas_NEM_ad_erteket(self) -> None:
        """Végtelen vagy nulla visszaadása csendes tévedés lenne."""
        fields = {"total": _ok(20.0), "cycle": _ok(0.0), "qty": _missing()}
        result, outcomes = apply_rules(fields, (SZORZAT,), 0.01)

        self.assertEqual(outcomes[0].status, "nem futott")
        self.assertIn("nullával", outcomes[0].detail)
        self.assertIsNone(result["qty"].value)


class GuardTests(unittest.TestCase):
    def test_a_LOGIKAI_ertek_nem_szam(self) -> None:
        """A `bool` a Pythonban `int`: egy logikai mező észrevétlenül 1-ként vennne
        részt a számtanban, és az egyenlőség attól „stimmelne", ami nem is szám."""
        fields = {"total": _ok(1.0), "cycle": _ok(True), "qty": _ok(1.0)}
        _, outcomes = apply_rules(fields, (SZORZAT,), 0.01)
        self.assertEqual(outcomes[0].status, "származtatva")  # a `cycle` hianyzonak szamit
        self.assertNotEqual(outcomes[0].status, "ok")

    def test_a_bemeneti_szotar_NEM_modosul(self) -> None:
        """A hívónak joga van látni, mi volt az OLVASOTT állapot a származtatás előtt."""
        fields = {"total": _missing(), "cycle": _ok(2.0), "qty": _ok(10.0)}
        eredeti = dict(fields)
        apply_rules(fields, (SZORZAT,), 0.01)
        self.assertEqual(fields, eredeti)

    def test_tul_sok_hianyzo_ertek_eseten_NEM_talalgat(self) -> None:
        fields = {"total": _missing(), "cycle": _missing(), "qty": _ok(10.0)}
        result, outcomes = apply_rules(fields, (SZORZAT,), 0.01)
        self.assertEqual(outcomes[0].status, "nem futott")
        self.assertIsNone(result["total"].value)
        self.assertIsNone(result["cycle"].value)


class RuleValidationTests(unittest.TestCase):
    def test_egy_operandusu_szabaly_nem_ellenoriz_semmit(self) -> None:
        with self.assertRaises(ConfigurationError):
            ConsistencyRule("rossz", "a", ("b",))

    def test_a_bal_oldal_nem_lehet_a_jobb_oldalon(self) -> None:
        """Az egyenlőség önmagát ellenőrizné — és mindig teljesülne."""
        with self.assertRaises(ConfigurationError) as ctx:
            ConsistencyRule("rossz", "a", ("a", "b"))
        self.assertIn("önmagát", str(ctx.exception))

    def test_nev_nelkuli_szabaly_diagnosztikaja_hasznalhatatlan_lenne(self) -> None:
        with self.assertRaises(ConfigurationError):
            ConsistencyRule("", "a", ("b", "c"))

    def test_negativ_tures(self) -> None:
        with self.assertRaises(ConfigurationError):
            ConsistencyRule("rossz", "a", ("b", "c"), tolerance=-1.0)


if __name__ == "__main__":
    unittest.main()
