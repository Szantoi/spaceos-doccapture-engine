"""A naplózás kapuja — a napló nem szivárogtathat (QUALITY §3 + §7).

Két dolgot mérünk, és mindkettő KÁR, nem stílus:

1. **titok a naplóban** — a log-fájl hozzáférés-védelme gyakran lazább, mint az
   adatbázisé;
2. **abszolút útvonal a naplóban** — a `SourceEvidence` szerződéséből
   szándékosan kihagytuk; értelmetlen lenne a log-fájlba beírni.

⚠ A legfontosabb teszt itt a `LiveCallSiteTests`: nem azt méri, hogy a *kapu*
működik, hanem hogy a **valódi napló-hívások** átmennek rajta. Egy kapu, amit a
saját kódunk nem hív, ugyanolyan haszontalan, mint egy mindig zöld teszt.
"""

from __future__ import annotations

import ast
import logging
import tempfile
import unittest
from pathlib import Path

from doccapture.core.config import CaptureConfig
from doccapture.core.observability import (
    LOGGER_NAME,
    RedactionError,
    assert_safe_fields,
    get_logger,
    log_step,
)
from doccapture.core.tabular import ColumnSpec, ColumnType, TableSchema
from doccapture.infrastructure.tabular.delimited import DelimitedTabularReader

SRC = Path(__file__).resolve().parent.parent / "src" / "doccapture"


class RedactionGateTests(unittest.TestCase):
    def test_titkot_sejteto_KULCS_elbukik(self) -> None:
        """A kulcs NEVE alapján tiltunk: az érték felismerése találgatás lenne."""
        for kulcs in ("api_key", "access_token", "db_password", "client_secret",
                      "credential_value"):
            with self.subTest(kulcs=kulcs):
                with self.assertRaises(RedactionError):
                    assert_safe_fields({kulcs: "barmi"})

    def test_abszolut_ut_elbukik_mindket_irasmoddal(self) -> None:
        for ut in ("/home/valaki/forras.csv", "C:\\Users\\valaki\\forras.csv",
                   "C:/Users/valaki/forras.csv", "\\\\halozat\\megosztas\\f.csv"):
            with self.subTest(ut=ut):
                with self.assertRaises(RedactionError):
                    assert_safe_fields({"source": ut})

    def test_a_RELATIV_ut_atmegy(self) -> None:
        """A másik irány: egy mindig-tiltó kapu használhatatlanná tenné a naplót."""
        assert_safe_fields({"source": "alkonyvtar/arlista.csv"})
        assert_safe_fields({"source": "arlista.csv"})
        assert_safe_fields({"rows": 12, "truncated": False})

    def test_a_kapu_HIBAT_dob_nem_csendben_hagyja_ki(self) -> None:
        """Ha csendben elhagynánk a mezőt, a fejlesztő azt hinné, naplózott — és a
        hiba akkor derülne ki, amikor épp kellene a napló."""
        with self.assertRaises(RedactionError):
            log_step(get_logger("proba"), "proba", api_key="x")


class ConsistencyWithConfigTests(unittest.TestCase):
    """A napló tiltólistája és a config tiltólistája **ugyanaz a szabály**.

    Ha a kettő elcsúszik, az egyik előbb-utóbb hazudni fog — ezért teszt köti
    össze őket, nem konvenció.
    """

    def test_a_ket_tiltolista_ugyanazt_a_kulcsot_fogja(self) -> None:
        from doccapture.core import config as config_modul
        from doccapture.core import observability as naplo_modul

        config_hints = set(config_modul._SECRET_HINTS)
        naplo_hints = set(naplo_modul._FORBIDDEN_KEY_HINTS)
        self.assertTrue(
            config_hints <= naplo_hints,
            f"a config tilt olyan kulcsot, amit a napló átengedne: "
            f"{sorted(config_hints - naplo_hints)}",
        )

    def test_amit_a_config_titoknak_tart_azt_a_naplo_is(self) -> None:
        """Konkrét, nem halmaz-szintű bizonyíték: ugyanaz a mező mindkettőn elbukik."""
        config = CaptureConfig()
        config.api_key = "ertek"  # type: ignore[attr-defined]
        from doccapture.core.errors import ConfigurationError

        with self.assertRaises(ConfigurationError):
            config.assert_no_secret_values()
        with self.assertRaises(RedactionError):
            assert_safe_fields({"api_key": "ertek"})


class LiveCallSiteTests(unittest.TestCase):
    """A VALÓDI napló-hívások átmennek-e a kapun.

    Ez a fájl legfontosabb tesztje: a kapu megléte nem bizonyít semmit, ha a
    saját kódunk nem hívja, vagy ha olyan mezőt ad át, amit a kapu tiltana.
    """

    def test_a_tablazatos_ut_TENYLEG_naplozik(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "arlista.csv").write_text(
                "Kód;Mennyiség\nA-1;1\n;\n", encoding="utf-8"
            )
            schema = TableSchema(
                columns=(
                    ColumnSpec("kod", ("Kód",), ColumnType.TEXT, required=True),
                    ColumnSpec("db", ("Mennyiség",), ColumnType.NUMBER),
                ),
                identity_keys=("kod",),
            )
            reader = DelimitedTabularReader(CaptureConfig(input_root=tmp))

            with self.assertLogs(LOGGER_NAME, level=logging.INFO) as fogott:
                reader.read("arlista.csv", schema)

        uzenetek = "\n".join(fogott.output)
        # Szerkezet es darabszam IGEN...
        self.assertIn("delimited.read", uzenetek)
        self.assertIn("tabular.assemble", uzenetek)
        self.assertIn("rows=1", uzenetek)
        self.assertIn("skipped_blank=1", uzenetek)
        self.assertIn("source=arlista.csv", uzenetek)
        # ...TARTALOM viszont NEM: a cellaertek nem kerul a naploba.
        self.assertNotIn("A-1", uzenetek)

    def test_a_naplo_nem_ir_ki_abszolut_utat(self) -> None:
        """Az adapter a relatív utat naplózza — pedig abszolúttal dolgozik.
        Ha ez elcsúszik, a napló felfedi a gépi könyvtárszerkezetet."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "arlista.csv").write_text("Kód;Mennyiség\nA-1;1\n", encoding="utf-8")
            schema = TableSchema(columns=(ColumnSpec("kod", ("Kód",), required=True),))
            reader = DelimitedTabularReader(CaptureConfig(input_root=tmp))

            with self.assertLogs(LOGGER_NAME, level=logging.INFO) as fogott:
                reader.read("arlista.csv", schema)

        uzenetek = "\n".join(fogott.output)
        self.assertNotIn(tmp, uzenetek, "a naploba bekerult a bemeneti gyoker abszolut utja")


class LoggerOwnershipTests(unittest.TestCase):
    def test_a_mag_nem_konfiguralja_a_gyoker_naplozot(self) -> None:
        """Egy könyvtár, ami magához ragadja a gyökér-naplózót, elveszi a döntést
        a fogyasztótól — és a beágyazó alkalmazás naplója összeomlik tőle."""
        tilos = ("basicConfig", "addHandler", "setLevel", "disable")
        vetkesek: dict[str, list[str]] = {}
        for modul in sorted(SRC.rglob("*.py")):
            forras = modul.read_text(encoding="utf-8")
            talalat = [
                node.func.attr
                for node in ast.walk(ast.parse(forras))
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in tilos
            ]
            if talalat:
                vetkesek[modul.relative_to(SRC).as_posix()] = talalat
        self.assertEqual(vetkesek, {}, f"a csomag konfiguralja a naplozast: {vetkesek}")

    def test_minden_naplozo_a_motor_fa_alatt_van(self) -> None:
        """Egy `logging.getLogger("valami")` a fa mellé kerülne, és a fogyasztó
        nem tudná egy névvel elhallgattatni az egész motort."""
        self.assertTrue(get_logger().name == LOGGER_NAME)
        self.assertTrue(get_logger("tabular").name.startswith(f"{LOGGER_NAME}."))

        vetkesek: dict[str, int] = {}
        for modul in sorted(SRC.rglob("*.py")):
            forras = modul.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(forras)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "getLogger"
                    and modul.name != "observability.py"
                ):
                    vetkesek[modul.relative_to(SRC).as_posix()] = node.lineno
        self.assertEqual(
            vetkesek,
            {},
            f"kozvetlen getLogger hivas a fan kivul: {vetkesek} — hasznald a get_logger()-t",
        )


if __name__ == "__main__":
    unittest.main()
