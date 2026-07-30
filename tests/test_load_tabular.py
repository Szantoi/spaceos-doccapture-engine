"""A táblázatos betöltő use-case: útválasztás, zaj-szűrés, mértékegység, határ.

Amit itt mérünk, az nem az olvasás (azt az adapter-tesztek fedik), hanem a
**döntések**: melyik fájlt vesszük fel egyáltalán, melyik adapter olvassa, és mi
kerül a rekordba — különösen az, hogy **hol áll meg a motor**.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.models import CaptureRecord, Confidence, InputKind
from doccapture.core.ports import TabularReader
from doccapture.core.tabular import ColumnSpec, ColumnType, TableSchema, TabularOptions
from doccapture.core.tabular.result import TabularReadResult
from doccapture.usecases.load_tabular import UNIT_FIELD_PREFIX, TabularLoader

SCHEMA = TableSchema(
    columns=(
        ColumnSpec("kod", ("Kód",), ColumnType.TEXT, required=True),
        ColumnSpec("mennyiseg", ("Mennyiség",), ColumnType.NUMBER),
    ),
    identity_keys=("kod",),
)


class _SpyReader(TabularReader):
    """Olvasó-helyettes: rögzíti, hogy meghívták-e és mivel."""

    def __init__(self, result: TabularReadResult | None = None) -> None:
        self.calls: list[tuple[str, TableSchema]] = []
        self._result = result or TabularReadResult()

    def read(self, relative_path: str, schema: TableSchema) -> TabularReadResult:
        self.calls.append((relative_path, schema))
        return self._result


class _Source:
    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def write(self, name: str, content: str) -> str:
        (self.root / name).write_text(content, encoding="utf-8")
        return name

    def config(self, **kwargs) -> CaptureConfig:
        return CaptureConfig(input_root=str(self.root), **kwargs)

    def close(self) -> None:
        self._tmp.cleanup()


class RoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = _Source()
        self.addCleanup(self.source.close)

    def test_a_munkafuzet_es_a_szoveges_ut_KULON_adapterre_megy(self) -> None:
        """A négy bemenet négy külön út — és ez itt, az útválasztásban látszik."""
        delimited, workbook = _SpyReader(), _SpyReader()
        loader = TabularLoader(
            self.source.config(), delimited_reader=delimited, workbook_reader=workbook
        )
        self.source.write("lista.csv", "Kód;Mennyiség\nA-1;1\n")
        self.source.write("lista.xlsx", "nem is kell ervenyes tartalom")

        loader.load("lista.csv", SCHEMA)
        loader.load("lista.xlsx", SCHEMA)

        self.assertEqual([c[0] for c in delimited.calls], ["lista.csv"])
        self.assertEqual([c[0] for c in workbook.calls], ["lista.xlsx"])

    def test_a_NEM_tablazatos_ut_kimondott_hiba(self) -> None:
        """Egy dokumentumot táblázatként olvasni nem hibát ad, hanem SZEMETET —
        és a szemét úgy néz ki, mint az adat."""
        delimited = _SpyReader()
        loader = TabularLoader(self.source.config(), delimited_reader=delimited)
        self.source.write("szamla.pdf", "x")

        with self.assertRaises(SourceUnreadableError) as ctx:
            loader.load("szamla.pdf", SCHEMA)
        self.assertIn("text_layer_document", str(ctx.exception))
        self.assertEqual(delimited.calls, [], "megis megprobalta beolvasni")

    def test_ismeretlen_kiterjesztes_kimondott_hiba(self) -> None:
        loader = TabularLoader(self.source.config(), delimited_reader=_SpyReader())
        self.source.write("jegyzet.txt", "x")

        with self.assertRaises(SourceUnreadableError) as ctx:
            loader.load("jegyzet.txt", SCHEMA)
        self.assertIn("Nem támogatott", str(ctx.exception))


class NoiseFileTests(unittest.TestCase):
    """M12: minden éles mappában van biztonsági másolat és lock-fájl."""

    def setUp(self) -> None:
        self.source = _Source()
        self.addCleanup(self.source.close)

    def test_a_zaj_fajlokat_KIZARJUK_es_nem_is_olvassuk(self) -> None:
        delimited = _SpyReader()
        loader = TabularLoader(self.source.config(), delimited_reader=delimited)

        for name in ("~$lista.csv", "lista.csv.bak", ".~lock.lista.csv#"):
            with self.subTest(name=name):
                self.source.write(name, "Kód;Mennyiség\nA-1;1\n")
                with self.assertRaises(SourceUnreadableError) as ctx:
                    loader.load(name, SCHEMA)
                self.assertIn("kizárási listán", str(ctx.exception))

        self.assertEqual(delimited.calls, [], "zaj-fajlt olvasott be")

    def test_a_rendes_fajl_ATMEGY_a_szuron(self) -> None:
        """A másik irány: egy mindent kizáró szűrő ugyanolyan haszontalan."""
        delimited = _SpyReader()
        loader = TabularLoader(self.source.config(), delimited_reader=delimited)
        self.source.write("lista.csv", "Kód;Mennyiség\nA-1;1\n")

        loader.load("lista.csv", SCHEMA)
        self.assertEqual(len(delimited.calls), 1)

    def test_a_kizarasi_lista_KONFIGURACIO(self) -> None:
        """Rendszerenként más — ha kódba lenne írva, minden bevezetésnél
        forrás-módosítás kellene."""
        loader = TabularLoader(
            self.source.config(excluded_name_patterns=["*_regi.csv"]),
            delimited_reader=_SpyReader(),
        )
        self.source.write("lista_regi.csv", "Kód;Mennyiség\nA-1;1\n")
        self.source.write("~$lista.csv", "Kód;Mennyiség\nA-1;1\n")

        with self.assertRaises(SourceUnreadableError):
            loader.load("lista_regi.csv", SCHEMA)
        # A sajat lista FELULIRJA az alapertelmezest -- ez a `~$` mar atmegy.
        loader.load("~$lista.csv", SCHEMA)


class RecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = _Source()
        self.addCleanup(self.source.close)
        self.source.write(
            "arlista.csv",
            "Kód;Mennyiség (m2)\n"
            "A-1;12,5\n"
            ";\n"
            "A-2;kb. 3\n",
        )
        self.loader = TabularLoader(
            self.source.config(tabular=TabularOptions(decimal_separator=","))
        )
        self.record = self.loader.load("arlista.csv", SCHEMA)

    def test_a_rekord_a_TABLAZATOS_utat_rogziti(self) -> None:
        self.assertIsInstance(self.record, CaptureRecord)
        self.assertIs(self.record.input_kind, InputKind.TABULAR)

    def test_a_rekordnak_van_FAJL_szintu_bizonyiteka(self) -> None:
        self.assertEqual(self.record.evidence.relative_path, "arlista.csv")
        self.assertTrue(self.record.evidence.content_hash.startswith("sha256:"))

    def test_a_MERTEKEGYSEG_adatta_valik_bizonyitekkal(self) -> None:
        """M15: megőrizzük, de nem tesszük fel — és nem is váltjuk át."""
        field = self.record.fields[f"{UNIT_FIELD_PREFIX}mennyiseg"]
        self.assertEqual(field.value, "m2")
        self.assertIs(field.confidence, Confidence.CONFIRMED)
        self.assertEqual(field.evidence.locator, "R1")
        self.assertIn("NEM átváltva", field.note)

    def test_a_szamok_ATVALTAS_NELKUL_jonnek(self) -> None:
        """Az egység `m2`, de a 12,5 marad 12,5 — a konverzió a fogyasztó
        explicit, naplózott döntése, nem a miénk."""
        self.assertEqual(self.record.rows[0]["mennyiseg"].value, 12.5)

    def test_az_ertelmezhetetlen_ertek_HIANY_es_a_rekord_jelzi(self) -> None:
        self.assertIs(self.record.rows[1]["mennyiseg"].confidence, Confidence.MISSING)
        self.assertTrue(self.record.needs_human)

    def test_a_kihagyott_ures_sor_a_DIAGNOSZTIKABAN_van(self) -> None:
        self.assertEqual(len(self.record.rows), 2)
        self.assertTrue(
            any("1 sor üresként kihagyva" in note for note in self.record.diagnostics),
            self.record.diagnostics,
        )


class BoundaryTests(unittest.TestCase):
    """Ahol a motor MEGÁLL. Ez a G1/G2 határ, és ez az utolsó pont, ahol be
    lehetne csúsztatni egy „segítő" párosítást."""

    def test_a_rekord_NEM_tartalmaz_parositast_vagy_atvaltast(self) -> None:
        source = _Source()
        self.addCleanup(source.close)
        source.write("lista.csv", "Kód;Mennyiség (m2)\nA-1;2\n")

        record = TabularLoader(source.config()).load("lista.csv", SCHEMA)

        # Csak az van benne, ami a papiron all: a kulcsok a sema kulcsai, es
        # egyetlen szarmaztatott/parositott mezo sincs.
        self.assertEqual(sorted(record.rows[0]), ["kod", "mennyiseg"])
        self.assertEqual(
            sorted(record.fields), [f"{UNIT_FIELD_PREFIX}mennyiseg"]
        )

    def test_a_motorban_nincs_szamla_specifikus_use_case(self) -> None:
        """G1 (Gábor, 2026-07-30): a bevételezés a gazda. Ez a kapu ezért marad."""
        import pkgutil

        import doccapture.usecases as usecases

        names = [module.name for module in pkgutil.iter_modules(usecases.__path__)]
        gyanus = [n for n in names if "invoice" in n.lower() or "szamla" in n.lower()]
        self.assertEqual(
            gyanus, [], f"szamla-specifikus use-case kerult a motorba: {gyanus}"
        )


if __name__ == "__main__":
    unittest.main()
