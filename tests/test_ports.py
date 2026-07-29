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
        """Ez a **G1** kapu tárgya: két igazság van kialakulóban ugyanarról.

        Amíg nincs döntés, a magba bemásolni azt jelentené, hogy a kérdést
        kódba írt tényként előredöntjük. Ha ez a teszt egyszer elbukik, az
        nem hiba — hanem jelzés, hogy valaki a kapu előtt lépett.
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
