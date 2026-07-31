"""A MERES teljessege: minden teszt-modul pontosan egy korben fut.

⚠ **Ezt a kaput egy sajat res hozta elo.** A `tools/measure_dependency_free.py`
modul-listaja lemaradt a kontraktus-tesztekrol: a teljes suite 268 tesztet
futtatott, a fuggoseg-mentes kor 232-t, a munkafuzet-tesztek 13-at — es
23 teszt **egyik korben sem** volt benne. A `232 zold` szam igy nem fedte azt,
amit fedni latszott, es errol **semmi nem szolt**.

A kapu ezert nem azt meri, hogy a listak "helyesek", hanem hogy **teljesek**:
minden teszt-modul vagy a fuggoseg-mentes korben van, vagy kimondottan a
munkafuzet-korben. Egy uj teszt-fajl, ami egyikben sem szerepel, itt bukik el.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

# ⚠ MINDHAROM kor-lista az ESZKOZBOL jon, nem itt all literalkent. A koroket a
# `measure_dependency_free.py` futtatja, tehat a felosztas forras-igazsaga ott
# van; ha itt masolat allna, ket kulonbozo tudas lenne ugyanarrol, es a kapu
# eppen azt a fajta elcsuszast nem venne eszre, ami ellen ved.
# (A DC-01a elott a munkafuzet-lista MEG itt allt, es az eszkoz nem tudott rola.)
from measure_dependency_free import (  # noqa: E402
    DEPENDENCY_FREE_MODULES,
    DOCUMENT_DEPENDENT_MODULES,
    WORKBOOK_DEPENDENT_MODULES,
)


def _discovered_modules() -> set[str]:
    return {
        f"tests.{path.stem}"
        for path in sorted((REPO / "tests").glob("test_*.py"))
    }


class MeasurementCompletenessTests(unittest.TestCase):
    def test_minden_teszt_modul_pontosan_EGY_korben_fut(self) -> None:
        discovered = _discovered_modules()
        # Ez a fajl maga nem meresi alany, hanem a meres kapuja.
        discovered.discard("tests.test_measurement_completeness")

        free = set(DEPENDENCY_FREE_MODULES)
        workbook = set(WORKBOOK_DEPENDENT_MODULES)
        document = set(DOCUMENT_DEPENDENT_MODULES)

        kimaradt = discovered - free - workbook - document
        self.assertEqual(
            kimaradt,
            set(),
            f"teszt-modul EGYIK merési korben sem szerepel: {sorted(kimaradt)}. "
            f"A 'fuggoseg nelkul N zold' szam igy nem fedi, amit fedni latszik.",
        )

        # Minden KOR-PART megvizsgalunk: harom kornel a `free & workbook`
        # egymagaban ket atfedest CSENDBEN atengedne.
        korok = {"fuggoseg-mentes": free, "munkafuzet": workbook, "dokumentum": document}
        nevek = sorted(korok)
        for i, egyik in enumerate(nevek):
            for masik in nevek[i + 1 :]:
                atfedes = korok[egyik] & korok[masik]
                self.assertEqual(
                    atfedes,
                    set(),
                    f"teszt-modul a(z) {egyik!r} ES a(z) {masik!r} korben is "
                    f"szerepel: {sorted(atfedes)} — ket igazsag ugyanarrol a szamrol.",
                )

    def test_a_listak_nem_hivatkoznak_NEM_LETEZO_modulra(self) -> None:
        """Egy elavult bejegyzes a listaban ertelmezhetetlen hibat adna a CI-ban."""
        discovered = _discovered_modules()
        for module in (
            *DEPENDENCY_FREE_MODULES,
            *WORKBOOK_DEPENDENT_MODULES,
            *DOCUMENT_DEPENDENT_MODULES,
        ):
            with self.subTest(module=module):
                self.assertIn(module, discovered, "elavult bejegyzes a meresi listaban")

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        """Egy kitalalt uj teszt-modul kimaradasa elbukna."""
        discovered = _discovered_modules() | {"tests.test_jovobeli_uj_modul"}
        kimaradt = (
            discovered
            - set(DEPENDENCY_FREE_MODULES)
            - set(WORKBOOK_DEPENDENT_MODULES)
            - set(DOCUMENT_DEPENDENT_MODULES)
        )
        kimaradt.discard("tests.test_measurement_completeness")
        self.assertEqual(kimaradt, {"tests.test_jovobeli_uj_modul"})


if __name__ == "__main__":
    unittest.main()
