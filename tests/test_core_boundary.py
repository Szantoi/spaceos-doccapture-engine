"""A hexagonális határ GÉPI kapuja.

A forrás-prototípus kimondta a szabályt („a magban TILOS infrastruktúra-import"),
de csak dokumentációban. Egy szabály, amit nem mér senki, előbb-utóbb megsérül —
és pont az ilyen sérülés az, ami csendben marad: a kód működik, csak éppen a
domain kezd tudni a külvilágról, és onnantól nem cserélhető az adapter.

Ezért itt kapu lesz belőle: a mag minden modulja csak a szabványkönyvtárat és
saját magát importálhatja.

⚠ **AMIT AZ IMPORT-KAPU EGYMAGÁBAN NEM FOG MEG (mérve, DC-01a)**
Az `allowed` halmaz a **teljes** szabványkönyvtár, tehát a magban `open()` +
`struct` párossal bináris fájlformátumot fejteni **zöld maradna** — pedig az
pont a hexagonális határ sértése: a domain fájlt nyitna. Ez ma nem elméleti
kockázat: a kereshető PDF írásánál (DC-01b) a betűtípus-fedés mérése kísértene
arra, hogy a mag beleolvasson egy font-fájlba. A rést **most** zárjuk be, amíg
nincs sértés — egy kaput sértés közben bevezetni mindig alku lesz.
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


# Fajlrendszer-hozzaferes alakjai. A `open` beepitett fuggveny; a tobbi a
# `Path`-on (es barmi mason) meghivhato METODUS-nev. Nev szerint tiltunk, nem
# tipus szerint: az AST-bol a tipus nem derul ki, es egy `p.read_bytes()` a
# magban akkor is hataratlepes, ha `p` eppen nem `Path`.
_FILESYSTEM_CALLS = frozenset(
    {
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "write_text",
        "unlink",
        "mkdir",
        "rename",
        "replace",
        "iterdir",
        "glob",
        "rglob",
    }
)

# A `replace` SZANDEKOSAN a listan van (atomikus fajl-csere alakja), de a
# `dataclasses.replace` ugyanezt a nevet viseli, es AZ nem fajlrendszer.
# Ezert a hivas-alakot is nezzuk: a `replace(...)` sima fuggvenykent
# (`ast.Name`) a dataclasses-e; a `valami.replace(...)` metoduskent
# (`ast.Attribute`) a gyanus. Ugyanez all a `str.replace`-re, ami viszont
# NEM fajl -- ezert a sztring-metodus alakot kulon kell kezelni, es a kapu
# ezt a KETERTELMUSEGET kimondja, nem elhallgatja.
_AMBIGUOUS_ATTRIBUTE_CALLS = frozenset({"replace", "glob"})


def filesystem_calls(source: str) -> set[str]:
    """A forrásban meghívott fájlrendszer-műveletek nevei (AST-ből).

    Kimondott korlát: ez **hívás-alak** vizsgálat, nem típus-vizsgálat. Egy
    `getattr(p, "read_" + "bytes")()` alakú kerülőút átmenne rajta — de az már
    szándékos megkerülés, nem véletlen határsértés, és a kapu célja az utóbbi.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            found.add("open")
        elif isinstance(func, ast.Attribute) and func.attr in _FILESYSTEM_CALLS:
            if func.attr in _AMBIGUOUS_ATTRIBUTE_CALLS:
                # `dataclasses.replace(...)` es `str.replace(...)` nem fajl-muvelet.
                # A megkulonboztetes csak a hivott objektumbol jonne, azt viszont
                # az AST nem tudja -- ezert ezeket NEM jelentjuk, es ezt a rest
                # kimondjuk itt, a kod mellett. (Ha valaha `Path.replace` kerul a
                # magba, azt a fenti import-kapu ugyis megfogja: a `pathlib` NEM
                # eleg hozza, mert az stdlib -- de a fajlt megnyitni `open` nelkul
                # nem lehet, es az ITT bukik.)
                continue
            found.add(func.attr)
    return found


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

    def test_a_mag_egyetlen_modulja_sem_NYIT_FAJLT(self) -> None:
        """A mag nem nyúlhat a fájlrendszerhez — az adapterek dolga.

        Az import-kapu ezt NEM fogja meg: az `open` beépített függvény, a
        `pathlib` pedig szabványkönyvtár, tehát mindkettő átmegy rajta. Egy
        magban nyitott fájl attól még határsértés, hogy stdlib-bel csinálják.
        """
        modules = sorted(CORE_DIR.rglob("*.py"))
        self.assertGreater(len(modules), 0, "Nem talaltam mag-modult — a kapu vakon zold lenne.")

        offenders: dict[str, set[str]] = {}
        for module in modules:
            found = filesystem_calls(module.read_text(encoding="utf-8"))
            if found:
                offenders[module.relative_to(CORE_DIR).as_posix()] = found

        self.assertEqual(
            offenders,
            {},
            f"A mag fajlrendszerhez nyul: {offenders}. A domain nem olvas es nem "
            f"ir fajlt — az adapter dolga. (Ha ez szandekos, a hataron kell "
            f"atvinni, nem a kaput gyengiteni.)",
        )

    # --- negativ kontroll: bizonyitjuk, hogy a kapu HARAP ---------------

    def test_a_fajlrendszer_kapu_HARAP(self) -> None:
        """Enélkül nem tudnánk, hogy a fenti teszt mér-e egyáltalán valamit.

        Mérve: a mai magra a kapu üres halmazt ad — ez a szám csak akkor
        bizonyíték, ha megmutatjuk, hogy a **nem üres** eset létezik.
        """
        self.assertEqual(
            filesystem_calls("with open('a.bin', 'rb') as f:\n    data = f.read()\n"),
            {"open"},
        )
        self.assertEqual(
            filesystem_calls("from pathlib import Path\ndata = Path('a').read_bytes()\n"),
            {"read_bytes"},
        )

    def test_a_fajlrendszer_kapu_NEM_VAKLARMA(self) -> None:
        """A másik irány: egy mindig-piros kapu ugyanolyan haszontalan.

        A `dataclasses.replace` és a `str.replace` neve egyezik egy
        fájl-művelettel — ezek NEM buktathatják el a magot.
        """
        source = (
            "from dataclasses import replace\n"
            "uj = replace(regi, mezo=1)\n"
            "szoveg = 'a-b'.replace('-', '_')\n"
            "elemek = [x for x in valami]\n"
        )
        self.assertEqual(filesystem_calls(source), set())

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
