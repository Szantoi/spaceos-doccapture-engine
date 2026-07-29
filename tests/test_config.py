"""A config szabályai — a beégetés és a titok-szivárgás gépi kapuja.

A tesztek nem a dataclasst mérik, hanem azt, hogy a config **kikényszeríti** a
szabályokat: titok nem kerülhet bele, és a biztonságos viselkedés az
alapértelmezés (nem az, amit be kell kapcsolni).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import ConfigurationError
from doccapture.core.models import InputKind


class SecretLeakTests(unittest.TestCase):
    """A forrás-prototípus configjában volt kulcs-mező, ÉS a config kiírta magát
    JSON-ba — vagyis a titok lemezre került. Ez itt nem fordulhat elő."""

    def test_titkot_sejteto_mezobe_nem_kerulhet_ertek(self) -> None:
        config = CaptureConfig()
        # Futasidoben adunk hozza egy ilyen mezot, mert a dataclass-ban
        # SZANDEKOSAN nincs -- a kapu attol is vedjen, ha valaki kesobb felvesz egyet.
        config.api_key = "b4rmilyen-ertek"  # type: ignore[attr-defined]
        with self.assertRaises(ConfigurationError) as ctx:
            config.assert_no_secret_values()
        self.assertIn("api_key", str(ctx.exception))

    def test_a_credential_env_kivetel_mert_csak_NEVEKET_tarol(self) -> None:
        """A változó-hivatkozás nem titok — ha ezt is buktatnánk, a kaput
        egy héten belül kikapcsolná valaki, és rosszabbul állnánk, mint kapu nélkül."""
        config = CaptureConfig(credential_env={"visual": "DOCCAPTURE_VISUAL_TOKEN"})
        config.assert_no_secret_values()  # nem dobhat
        self.assertIn("credential_env", config.to_dict())

    def test_a_dataclass_nem_definial_titok_mezot(self) -> None:
        """A legjobb védelem, ha nincs is hova beírni."""
        hints = ("key", "secret", "token", "password")
        offenders = [
            f.name
            for f in fields(CaptureConfig)
            if f.name != "credential_env" and any(h in f.name.lower() for h in hints)
        ]
        self.assertEqual(offenders, [])

    def test_titkot_tartalmazo_configot_nem_ir_ki(self) -> None:
        """Fail-closed: a mentés inkább bukjon el, mint hogy titkot írjon lemezre."""
        config = CaptureConfig()
        config.access_token = "nem-kerulhet-lemezre"  # type: ignore[attr-defined]
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "config.json")
            with self.assertRaises(ConfigurationError):
                config.save(str(target))
            self.assertFalse(target.exists(), "A fajl letrejott, pedig el kellett volna buknia.")


class SafeDefaultTests(unittest.TestCase):
    """A biztonságos viselkedés legyen az ALAPÉRTELMEZÉS, ne a bekapcsolható extra."""

    def test_a_forras_alapertelmezesben_csak_olvashato(self) -> None:
        self.assertTrue(CaptureConfig().read_only_source)

    def test_aktiv_tartalmat_alapertelmezesben_nem_futtatunk(self) -> None:
        self.assertFalse(CaptureConfig().run_active_content)

    def test_a_mertekegyseget_alapertelmezesben_megorizzuk(self) -> None:
        self.assertTrue(CaptureConfig().preserve_original_units)

    def test_a_zajfajl_kizaras_nem_ures(self) -> None:
        """Konfigurálható, de az alapértelmezés fedje a leggyakoribbakat —
        különben minden bevezetés ugyanazzal a felfedezéssel kezdődik."""
        self.assertIn("~$*", CaptureConfig().excluded_name_patterns)


class RoutingTests(unittest.TestCase):
    def test_a_tablazatos_bemenet_nem_a_felismero_utra_megy(self) -> None:
        routing = CaptureConfig().extension_routing
        self.assertEqual(routing[".xlsx"], InputKind.TABULAR)
        self.assertEqual(routing[".csv"], InputKind.TABULAR)

    def test_a_kepek_a_raszteres_utra_mennek(self) -> None:
        self.assertEqual(CaptureConfig().extension_routing[".png"], InputKind.RASTER_SCAN)


class RoundTripTests(unittest.TestCase):
    def test_mentes_es_betoltes_megorzi_a_bemenet_fajtakat(self) -> None:
        config = CaptureConfig(input_root="forras", retry_attempts=7)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "config.json")
            config.save(str(target))
            loaded = CaptureConfig.load(str(target))

        self.assertEqual(loaded.input_root, "forras")
        self.assertEqual(loaded.retry_attempts, 7)
        self.assertEqual(loaded.extension_routing[".pdf"], InputKind.TEXT_LAYER_DOCUMENT)

    def test_ismeretlen_bemenet_fajta_INDULASKOR_bukik(self) -> None:
        """Ne feldolgozás közben derüljön ki, hogy elgépelték."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "config.json")
            target.write_text(
                json.dumps({"extension_routing": {".pdf": "nincs_ilyen_ut"}}),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError):
                CaptureConfig.load(str(target))


if __name__ == "__main__":
    unittest.main()
