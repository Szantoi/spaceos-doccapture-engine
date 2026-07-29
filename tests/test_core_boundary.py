"""A hexagonális határ GÉPI kapuja.

A forrás-prototípus kimondta a szabályt („a magban TILOS infrastruktúra-import"),
de csak dokumentációban. Egy szabály, amit nem mér senki, előbb-utóbb megsérül —
és pont az ilyen sérülés az, ami csendben marad: a kód működik, csak éppen a
domain kezd tudni a külvilágról, és onnantól nem cserélhető az adapter.

Ezért itt kapu lesz belőle: a mag minden modulja csak a szabványkönyvtárat és
saját magát importálhatja.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "src" / "doccapture" / "core"
OWN_PACKAGE = "doccapture"


def imported_root_modules(source: str) -> set[str]:
    """A forrásban importált gyökér-modulnevek (AST-ből, futtatás nélkül).

    Azért AST-ből és nem importálással: egy hibás import futtatáskor derülne ki,
    és a kapu maga is elbukna attól, amit mérni akar.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # A relativ import (level > 0) sajat csomagon belul marad.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def infrastructure_imports(source: str) -> set[str]:
    """Amit a mag NEM importálhat: se külső csomag, se saját infrastruktúra."""
    allowed = set(sys.stdlib_module_names) | {"__future__", OWN_PACKAGE}
    return {name for name in imported_root_modules(source) if name not in allowed}


class CoreBoundaryTests(unittest.TestCase):
    def test_a_mag_egyetlen_modulja_sem_importal_infrastrukturat(self) -> None:
        # rglob es NEM glob: a `glob("*.py")` nem megy be alkonyvtarba, tehat egy
        # kesobb letrehozott `core/valami/` alcsomag CSENDBEN kimaradna, es a kapu
        # zold maradna. Megmerve: glob=6, rglob=7 egy alcsomaggal — a kulonbseg
        # pont az a fajl, amiben infra-import volt.
        modules = sorted(CORE_DIR.rglob("*.py"))
        self.assertGreater(len(modules), 0, "Nem talaltam mag-modult — a kapu vakon zold lenne.")

        offenders: dict[str, set[str]] = {}
        for module in modules:
            found = infrastructure_imports(module.read_text(encoding="utf-8"))
            if found:
                # Relativ ut es nem `module.name`: alcsomaggal ket azonos nevu
                # fajl (pl. `core/models.py` es `core/valami/models.py`) ugyanarra
                # a kulcsra kerulne, es az egyik talalat CSENDBEN elveszne.
                offenders[module.relative_to(CORE_DIR).as_posix()] = found

        self.assertEqual(
            offenders,
            {},
            f"A magban infrastruktura-import van: {offenders}. "
            f"A domain nem tudhat arrol, mi szolgalja ki — kulonben az adapter "
            f"nem cserelheto.",
        )

    def test_a_mag_csak_sajat_magat_importalja_a_csomagbol(self) -> None:
        """A mag nem nyúlhat az `infrastructure` vagy `usecases` rétegbe.

        Az előző teszt ezt nem fogná meg: a `doccapture` gyökér engedélyezett,
        tehát a `doccapture.infrastructure` átcsúszna rajta.
        """
        offenders: dict[str, list[str]] = {}
        for module in sorted(CORE_DIR.rglob("*.py")):
            source = module.read_text(encoding="utf-8")
            bad = [
                node.module
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith(f"{OWN_PACKAGE}.")
                and not node.module.startswith(f"{OWN_PACKAGE}.core")
            ]
            if bad:
                offenders[module.relative_to(CORE_DIR).as_posix()] = bad

        self.assertEqual(
            offenders, {}, f"A mag kifele importal a sajat csomagon belul: {offenders}"
        )

    # --- negativ kontroll: bizonyitjuk, hogy a kapu HARAP ---------------

    def test_a_kapu_megfogja_a_kulso_csomagot(self) -> None:
        """Enélkül nem tudnánk, hogy a fenti két teszt azért zöld, mert tiszta
        a mag — vagy azért, mert a mérés sosem talál semmit."""
        self.assertEqual(
            infrastructure_imports("import valamilyen_kulso_csomag\n"),
            {"valamilyen_kulso_csomag"},
        )

    def test_a_kapu_atengedi_a_szabvanykonyvtarat_es_a_sajat_magot(self) -> None:
        """A másik irány: egy mindig-piros kapu ugyanolyan haszontalan."""
        source = (
            "from __future__ import annotations\n"
            "import json\n"
            "from dataclasses import dataclass\n"
            "from doccapture.core.models import Confidence\n"
        )
        self.assertEqual(infrastructure_imports(source), set())


if __name__ == "__main__":
    unittest.main()
