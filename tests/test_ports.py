"""A portok szabályai.

Két dolgot mérünk, amit könnyű elveszíteni:
1. a port tényleg absztrakt (nem lehet véletlenül példányosítani),
2. a **négy bemenet négy külön útja** portokban is látszik — és a G1 kapu
   tárgya NEM csúszik vissza a magba.
"""

from __future__ import annotations

import inspect
import unittest

from doccapture.core import ports


class AbstractnessTests(unittest.TestCase):
    def test_minden_port_absztrakt(self) -> None:
        port_classes = [
            obj
            for name, obj in inspect.getmembers(ports, inspect.isclass)
            if obj.__module__ == ports.__name__ and issubclass(obj, ports.ABC)
        ]
        self.assertGreater(len(port_classes), 0, "Nem talaltam portot — a teszt vakon zold lenne.")

        for cls in port_classes:
            with self.subTest(port=cls.__name__):
                with self.assertRaises(TypeError):
                    cls()  # type: ignore[abstract]


class FourPathTests(unittest.TestCase):
    """A négy bemenet négy külön út — ha ez összeolvad, a legolcsóbb esetet
    fizetjük meg a legdrágábban."""

    def test_a_tablazatos_utnak_sajat_portja_van(self) -> None:
        self.assertTrue(hasattr(ports, "TabularReader"))

    def test_a_tablazatos_port_a_SEMAT_parameterkent_kapja(self) -> None:
        """Egy adapter ugyanabban a bevezetésben több különböző táblát olvas
        (árlista, cikktörzs, beszállítói lista). Ha a séma konstruktor-adat
        lenne, minden táblához külön adapter-példány kellene."""
        signature = inspect.signature(ports.TabularReader.read)
        self.assertEqual(
            list(signature.parameters), ["self", "relative_path", "schema"]
        )

    def test_a_tablazatos_port_a_DIAGNOSZTIKAT_is_visszaadja(self) -> None:
        """⚠ Ez a port eredetileg csak sorokat adott vissza (`read_rows`), és az
        ELSŐ adapter megépítése mérte meg, hogy ez szűk: az adapternek el kellett
        volna dobnia az illesztetlen fejléceket, a kihagyott sorok számát, a
        felismert mértékegységeket és a gyorsítótár-hiányt.

        Egy port, ami a diagnosztika eldobására kényszerít, **csendes
        adatvesztést tervez be** — ha nincs hova írni, nem lesz megírva.
        """
        result_type = ports.TabularReadResult
        for field_name in (
            "rows",
            "units",
            "diagnostics",
            "skipped_blank_rows",
            "unmatched_headers",
            "truncated",
        ):
            with self.subTest(field=field_name):
                self.assertIn(field_name, result_type.__dataclass_fields__)

    def test_a_regi_szuk_port_alak_MAR_NINCS(self) -> None:
        """Ha visszakerülne, két igazság lenne ugyanarról az olvasásról."""
        self.assertFalse(hasattr(ports.TabularReader, "read_rows"))

    def test_a_szovegreteges_es_a_raszteres_ut_kulon_port(self) -> None:
        self.assertTrue(hasattr(ports, "TextLayerReader"))
        self.assertTrue(hasattr(ports, "RasterTextReader"))
        self.assertIsNot(ports.TextLayerReader, ports.RasterTextReader)

    def test_a_kezirasnak_sajat_portja_van(self) -> None:
        self.assertTrue(hasattr(ports, "HandwritingTranscriber"))

    def test_a_szovegreteg_letezese_kerdezheto(self) -> None:
        """A kiterjesztés nem tudja megmondani, van-e szövegréteg — ezért kell
        egy explicit kérdés, ami eldönti, melyik úton megy tovább."""
        self.assertIn("has_text_layer", ports.TextLayerReader.__abstractmethods__)


class GateTests(unittest.TestCase):
    def test_a_szamla_kinyerő_port_NINCS_a_magban(self) -> None:
        """**G1 ELDÖNTVE (Gábor, 2026-07-30): a bevételezés a gazda.**

        Ez a kapu korábban azért létezett, mert a kérdés nyitott volt — most
        azért marad, mert a válasz **megvan**: a számla-értelmezés az iparági
        rétegé, a motor bemenet-előkészítő. A kapu tehát nem ideiglenes
        védőkorlát, hanem a döntés **gépi** alakja.

        Ha ez a teszt egyszer elbukik, az nem hiba — hanem jelzés, hogy valaki
        egy meghozott döntést írt vissza kóddal.
        """
        gyanus = [
            name
            for name in dir(ports)
            if "invoice" in name.lower() or "szamla" in name.lower()
        ]
        self.assertEqual(
            gyanus,
            [],
            "Szamla-specifikus tipus kerult a magba a G1 dontes elott: "
            f"{gyanus}. Ez az iparagi reteg dolga, nem a motore.",
        )


if __name__ == "__main__":
    unittest.main()
