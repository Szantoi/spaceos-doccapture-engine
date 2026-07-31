"""A `docs/PRINCIPLES.md` kapuja — az elvek dokumentuma se csúszhasson el.

MIÉRT VAN EGYÁLTALÁN TESZT EGY DOKUMENTUMRA
-------------------------------------------
Az elv-táblázat összegző számát (*„10 elvet fed gépi kapu, 2-t részben, 3-at
nem"*) **első leírásnál elszámoltam**. Ez a fajta szám észrevétlenül csúszik el:
a tábla nő, az összegzés marad — és onnantól a dokumentum **állít**, nem mér.

Ez a fájl három dolgot köt össze:

1. az összegző szám **egyezik** a tábla tartalmával;
2. minden elv (M1-M15) **szerepel** a táblában — egy kimaradó elv csendben
   „nem is létezőnek" látszana;
3. amire a tábla **✅ kaput** ír, ahhoz **tényleg tartozik teszt-fájl**.

A 3. pont a legfontosabb: egy „✅" a dokumentumban a legkényelmesebb hazugság.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "PRINCIPLES.md"
TESTS = REPO / "tests"

# A tabla sorai: | **Mx** | leiras | kapu-allapot |
_ROW = re.compile(r"^\|\s*\*\*(M\d+)\*\*\s*\|(.+?)\|([^|]*)\|\s*$", re.M)
# ⚠ A toldalek SZAMFUGGO, es ezt a mero eszkoz elso valtozata nem tudta: a
# minta konkretan a "2-t reszben, 3-at egyaltalan nem" alakra volt szabva.
# Amikor az M2 allapota valtozott (3 reszben, 2 nem fedett), a HELYESEN irt
# magyar mondat ("3-at reszben, 2-t egyaltalan nem") mar nem illeszkedett, es a
# kapu ugy bukott el, hogy a doksi kozben igazat mondott.
# A javitas iranya fontos: NEM a mondatot rontjuk el a minta kedveert (az a
# mereshez igazitott valosag lenne), hanem a mintat tesszuk toldalek-turove.
_SUMMARY = re.compile(
    r"\*\*Mérve:\s*(\d+)\s*elvet fed gépi kapu,\s*(\d+)(?:-\w+)?\s*részben,\s*"
    r"(\d+)(?:-\w+)?\s*egyáltalán nem\*\*"
)


def _rows() -> dict[str, str]:
    """Elv-azonosító → a kapu-oszlop tartalma."""
    text = DOC.read_text(encoding="utf-8")
    return {m.group(1): m.group(3).strip() for m in _ROW.finditer(text)}


def _classify(cell: str) -> str:
    if cell.startswith("✅"):
        return "teljes"
    if cell.startswith("részben"):
        return "reszben"
    return "nincs"


class TableIntegrityTests(unittest.TestCase):
    def test_a_dokumentum_letezik(self) -> None:
        """Enélkül a többi teszt vakon zöld lenne."""
        self.assertTrue(DOC.is_file(), f"nincs meg: {DOC}")

    def test_MINDEN_elv_szerepel_a_tablaban(self) -> None:
        """Egy kimaradó elv csendben „nem is létezőnek" látszana."""
        expected = {f"M{i}" for i in range(1, 16)}
        self.assertEqual(set(_rows()), expected, "az elv-tabla hianyos vagy tulcsordult")

    def test_a_kapu_oszlop_MINDEN_sorban_ertelmezheto(self) -> None:
        """Egy üres vagy szabad szöveges kapu-oszlop nem mérhető állapot."""
        for principle, cell in _rows().items():
            with self.subTest(principle=principle):
                self.assertTrue(cell, "ures kapu-oszlop")
                self.assertIn(
                    _classify(cell),
                    {"teljes", "reszben", "nincs"},
                    f"nem ertelmezheto kapu-allapot: {cell!r}",
                )


class SummaryConsistencyTests(unittest.TestCase):
    """Az összegző szám EGYEZIK a táblával — ezt egyszer már elszámoltam."""

    def test_az_osszegzes_a_tablabol_kovetkezik(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        match = _SUMMARY.search(text)
        self.assertIsNotNone(match, "nem talalom az osszegzo mondatot")

        allitott = tuple(int(g) for g in match.groups())  # type: ignore[union-attr]
        rows = _rows()
        mert = (
            sum(1 for c in rows.values() if _classify(c) == "teljes"),
            sum(1 for c in rows.values() if _classify(c) == "reszben"),
            sum(1 for c in rows.values() if _classify(c) == "nincs"),
        )
        self.assertEqual(
            allitott,
            mert,
            f"az osszegzes ({allitott}) nem egyezik a tablaval ({mert}) — "
            f"a tabla nott, az osszegzes maradt",
        )

    def test_a_harom_szam_osszege_a_teljes_keszlet(self) -> None:
        rows = _rows()
        self.assertEqual(len(rows), 15)

    def test_a_NEM_fedett_elveket_a_szoveg_NEVESITI(self) -> None:
        """Egy szám a kimaradókról használhatatlan, ha nem tudod, MELYIKEK."""
        text = DOC.read_text(encoding="utf-8")
        nem_fedett = [p for p, c in _rows().items() if _classify(c) == "nincs"]
        self.assertTrue(nem_fedett, "a teszt vakon zold lenne, ha mindent fednenk")
        for principle in nem_fedett:
            with self.subTest(principle=principle):
                self.assertIn(
                    principle,
                    text.split("Mérve:")[1][:400],
                    f"a(z) {principle} nem fedett, de az osszegzes nem nevezi meg",
                )


class GateBackingTests(unittest.TestCase):
    """Amire a tábla ✅-t ír, ahhoz tartozzon TÉNYLEG teszt.

    Egy „✅" a dokumentumban a legkényelmesebb hazugság: senki nem ellenőrzi, és
    egy törölt teszt után is ott marad.
    """

    # Elv -> az a teszt-fajl, aminek a kaput hordoznia kell.
    BACKING = {
        "M3": "test_document_consistency.py",
        "M4": "test_document_consistency.py",
        "M6": "test_models.py",
        "M7": "test_tabular_values.py",
        "M8": "test_tabular_delimited.py",
        "M10": "test_tabular_delimited.py",
        "M11": "test_tabular_workbook.py",
        "M12": "test_load_tabular.py",
        "M13": "test_observability.py",
        "M15": "test_load_tabular.py",
    }

    def test_a_teljes_kapuk_LISTAJA_egyezik(self) -> None:
        """Ha egy elv ✅-t kap, de nincs mögötte megnevezett teszt-fájl, azt itt
        kell észrevenni — nem a következő auditon."""
        teljes = {p for p, c in _rows().items() if _classify(c) == "teljes"}
        self.assertEqual(
            teljes,
            set(self.BACKING),
            "a ✅-vel jelolt elvek es a megnevezett teszt-fajlok listaja elcsuszott",
        )

    def test_minden_megnevezett_teszt_fajl_LETEZIK(self) -> None:
        for principle, filename in sorted(self.BACKING.items()):
            with self.subTest(principle=principle):
                self.assertTrue(
                    (TESTS / filename).is_file(),
                    f"a(z) {principle} kapujat {filename} hordozna, de az nincs meg",
                )


if __name__ == "__main__":
    unittest.main()
