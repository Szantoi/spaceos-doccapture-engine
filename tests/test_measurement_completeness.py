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

from measure_dependency_free import DEPENDENCY_FREE_MODULES  # noqa: E402

# A munkafuzet-extrat igenylo modulok. KIMONDVA, nem kikovetkeztetve: ha egy modul
# `skipUnless`-szel vedett, azt itt kell nevesiteni, kulonben a kihagyasa csendben
# uresen zold szamlalot adna.
WORKBOOK_DEPENDENT_MODULES = ("tests.test_tabular_workbook",)


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

        kimaradt = discovered - free - workbook
        self.assertEqual(
            kimaradt,
            set(),
            f"teszt-modul EGYIK merési korben sem szerepel: {sorted(kimaradt)}. "
            f"A 'fuggoseg nelkul N zold' szam igy nem fedi, amit fedni latszik.",
        )

        mindkettoben = free & workbook
        self.assertEqual(
            mindkettoben,
            set(),
            f"teszt-modul MINDKET korben szerepel: {sorted(mindkettoben)} — "
            f"ket igazsag ugyanarrol a szamrol.",
        )

    def test_a_listak_nem_hivatkoznak_NEM_LETEZO_modulra(self) -> None:
        """Egy elavult bejegyzes a listaban ertelmezhetetlen hibat adna a CI-ban."""
        discovered = _discovered_modules()
        for module in (*DEPENDENCY_FREE_MODULES, *WORKBOOK_DEPENDENT_MODULES):
            with self.subTest(module=module):
                self.assertIn(module, discovered, "elavult bejegyzes a meresi listaban")

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        """Egy kitalalt uj teszt-modul kimaradasa elbukna."""
        discovered = _discovered_modules() | {"tests.test_jovobeli_uj_modul"}
        kimaradt = discovered - set(DEPENDENCY_FREE_MODULES) - set(WORKBOOK_DEPENDENT_MODULES)
        kimaradt.discard("tests.test_measurement_completeness")
        self.assertEqual(kimaradt, {"tests.test_jovobeli_uj_modul"})


if __name__ == "__main__":
    unittest.main()
