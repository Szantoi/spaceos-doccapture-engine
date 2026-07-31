"""Olvasási sorrend és hasáb-összeolvadás JELZÉSE (M2).

Ez a modul **függőség-mentesen** futtatható: a szabály a magban él, tehát a
mérés nem igényli a `document` extrát. Ezért az első mérési körbe kerül.

⚠ **A HAMIS-RIASZTÁSI KONTROLL ITT NEM DÍSZ.** Egy detektor, ami minden lapot
megjelöl, megkülönböztethetetlen attól, amelyik nem is fut — mindkettő
„jelzést ad", és mindkettő használhatatlan. Ezért minden jelzés-teszt párban
áll: a szépen szétvált hasábos lapon a detektor **nem szólalhat meg**.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from doccapture.core.columns import (  # noqa: E402
    detect_merged_columns,
    reading_order,
)
from doccapture.core.layout import PageLayout, TextFragment  # noqa: E402
from doccapture.core.text_layer_options import TextLayerOptions  # noqa: E402

LAP_SZELESSEG = 595.276
LAP_MAGASSAG = 841.89


def fragment(
    text: str, x_left: float, y_top: float = 100.0, width: float = 100.0
) -> TextFragment:
    return TextFragment(
        text=text,
        raw_confidence=1.0,
        x_left=x_left,
        y_top=y_top,
        x_right=x_left + width,
        y_bottom=y_top + 12.0,
    )


def page(fragments: list[TextFragment]) -> PageLayout:
    return PageLayout(
        source_name="irat.pdf#1",
        width=LAP_SZELESSEG,
        height=LAP_MAGASSAG,
        fragments=fragments,
    )


class ReadingOrderTests(unittest.TestCase):
    """A determinizmus közvetlen G2-nyereség: a prototípus ezt modellre bízta."""

    def test_fentrol_le_azon_belul_balrol_jobbra(self) -> None:
        jobb_felso = fragment("jobb-felso", x_left=320.0, y_top=100.0)
        bal_also = fragment("bal-also", x_left=72.0, y_top=200.0)
        bal_felso = fragment("bal-felso", x_left=72.0, y_top=100.0)

        rendezett = reading_order([jobb_felso, bal_also, bal_felso])

        self.assertEqual(
            [f.text for f in rendezett], ["bal-felso", "jobb-felso", "bal-also"]
        )

    def test_a_sorrend_UGYANAZ_barmilyen_bemeneti_sorrendbol(self) -> None:
        """Determinizmus: ez a lényeg, nem az, hogy „szép" a sorrend.

        Ha a sorrend a bemenettől függene, minden későbbi lépés (sor-összerakás,
        horgony-keresés) nem-determinisztikus bemenetet kapna — és a hiba
        futásonként máshol jelenne meg.
        """
        fragments = [
            fragment("a", x_left=72.0, y_top=100.0),
            fragment("b", x_left=320.0, y_top=100.0),
            fragment("c", x_left=72.0, y_top=200.0),
        ]
        vart = [f.text for f in reading_order(fragments)]

        for permutacio in (
            [fragments[2], fragments[0], fragments[1]],
            [fragments[1], fragments[2], fragments[0]],
            list(reversed(fragments)),
        ):
            with self.subTest(bemenet=[f.text for f in permutacio]):
                self.assertEqual([f.text for f in reading_order(permutacio)], vart)

    def test_azonos_geometriaju_fragmensek_is_STABIL_sorrendet_kapnak(self) -> None:
        """Döntetlennél a szöveg dönt — különben a sorrend a listán múlna."""
        egyik = fragment("alma", x_left=72.0, y_top=100.0)
        masik = fragment("banan", x_left=72.0, y_top=100.0)

        self.assertEqual([f.text for f in reading_order([masik, egyik])], ["alma", "banan"])
        self.assertEqual([f.text for f in reading_order([egyik, masik])], ["alma", "banan"])


class MergedColumnTests(unittest.TestCase):
    """M2: a gyanút JELÖLJÜK, nem vágjuk szét."""

    def test_az_osszeolvadt_hasab_JELZEST_kap(self) -> None:
        # A lapszelesseg ~84%-at atfogo egyetlen futam.
        osszeolvadt = fragment("bal es jobb hasab egyben", x_left=40.0, width=500.0)
        gyanuk = detect_merged_columns(page([osszeolvadt]), TextLayerOptions())

        self.assertEqual(len(gyanuk), 1)
        self.assertGreater(gyanuk[0].span_ratio, 0.6)
        self.assertIn("M2", gyanuk[0].reason, "a jelzes nevezze meg, MELYIK elvrol van szo")
        self.assertIn("%", gyanuk[0].reason, "a jelzes mondja ki a MERT aranyt")

    def test_a_JELZES_nem_valtoztatja_meg_a_fragmenst(self) -> None:
        """A szétvágás horgonya profil-adat (M1) — itt nem dönthető el."""
        osszeolvadt = fragment("bal es jobb hasab egyben", x_left=40.0, width=500.0)
        lap = page([osszeolvadt])

        detect_merged_columns(lap, TextLayerOptions())

        self.assertEqual(len(lap.fragments), 1, "a detektor NEM vaghat szet semmit")
        self.assertEqual(lap.fragments[0].text, "bal es jobb hasab egyben")

    # --- HAMIS-RIASZTASI KONTROLL --------------------------------------

    def test_a_szepen_szetvalt_hasabokon_NEM_szolal_meg(self) -> None:
        """Enélkül nem tudnánk, hogy a detektor különbséget tesz — vagy mindig szól."""
        bal = fragment("bal hasab", x_left=40.0, width=240.0)
        jobb = fragment("jobb hasab", x_left=320.0, width=240.0)

        gyanuk = detect_merged_columns(page([bal, jobb]), TextLayerOptions())

        self.assertEqual(
            gyanuk, [], "a szetvalt hasabokra adott jelzes hamis riasztas lenne"
        )

    def test_a_detektor_a_KUSZOBRE_lat(self) -> None:
        """Mutáció: küszöb=1.0 mellett az összeolvadt lapon SEM szólal meg.

        Ez bizonyítja, hogy a jelzés a beállított küszöbtől függ, nem attól,
        hogy a detektor „valamit mindig talál".
        """
        osszeolvadt = fragment("bal es jobb hasab egyben", x_left=40.0, width=500.0)
        lap = page([osszeolvadt])

        self.assertEqual(len(detect_merged_columns(lap, TextLayerOptions())), 1)
        self.assertEqual(
            detect_merged_columns(lap, TextLayerOptions(merged_span_ratio=1.0)),
            [],
            "1.0-s kuszob mellett csak a TELJES lapszelesseget atfogo futam gyanus",
        )

    def test_az_ertelmetlen_kuszob_INDULASKOR_bukik(self) -> None:
        """0-s küszöbnél minden fragmens gyanús lenne — az nem detektor."""
        from doccapture.core.errors import ConfigurationError

        with self.assertRaises(ConfigurationError):
            TextLayerOptions(merged_span_ratio=0.0).validate()


if __name__ == "__main__":
    unittest.main()
