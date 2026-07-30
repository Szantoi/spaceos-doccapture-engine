"""Forrás-higiénia: három kimondott vállalás, amit eddig SEMMI nem mért.

Mindhárom kapu egy konkrét, megtörtént eseményre válasz — nem elvont óvatosság.

1. **Homoglif azonosítóban.** Ebben a repóban **kétszer** csúszott be cirill `о`
   egy teszt-névbe, ugyanabban a munkakörben. Egy láthatatlan karakter egy
   azonosítóban a legrosszabb fajta hiba: a szem nem látja, a keresés nem találja
   meg, és két „ugyanolyan" név két különböző dolog lesz. Egy **visszatérő**
   hibamódra kapu jár, nem figyelem.

2. **`eval`/`exec` a csomagban.** A forrás-prototípus szűkített névtérrel
   kiértékelte a táblázat-képleteket, és ezt **kimondottan nem vettük át** — egy
   publikus termékben ez olyan minta, amit nem vállalunk. Egy vállalás, amit nem
   mér senki, előbb-utóbb megsérül.

3. **Abszolút útvonal a forrásban.** A bizonyíték-lánc tiltja, a napló-kapu
   tiltja — de a *forráskódban* álló abszolút út (egy elfelejtett hibakeresési
   útvonal) eddig szabadon átment volna, és **a repó publikus**.
"""

from __future__ import annotations

import ast
import re
import unicodedata
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCANNED = ("src", "tests", "tools")
CONFUSABLE_SCRIPTS = ("CYRILLIC", "GREEK")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for directory in SCANNED:
        files.extend(sorted((REPO / directory).rglob("*.py")))
    return files


def _is_confusable(ch: str) -> bool:
    if ord(ch) < 128:
        return False
    script = unicodedata.name(ch, "")
    return any(s in script for s in CONFUSABLE_SCRIPTS)


class HomoglyphTests(unittest.TestCase):
    """Latinnak látszó, de NEM latin betű egy azonosítóban."""

    def test_nincs_homoglif_azonosito_a_repoban(self) -> None:
        offenders: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.append(node.name)
                elif isinstance(node, ast.Name):
                    names.append(node.id)
                elif isinstance(node, ast.arg):
                    names.append(node.arg)
                for name in names:
                    bad = [c for c in name if _is_confusable(c)]
                    if bad:
                        offenders.append(
                            f"{path.relative_to(REPO).as_posix()}:{getattr(node, 'lineno', 0)} "
                            f"{name!r} ({unicodedata.name(bad[0])})"
                        )
        self.assertEqual(
            offenders,
            [],
            "latinnak latszo, de nem latin betu azonositoban: " + "; ".join(sorted(set(offenders))),
        )

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        """Enélkül nem tudnánk, hogy a fenti teszt azért zöld, mert tiszta a repó
        — vagy azért, mert a mérés sosem talál semmit."""
        cirill_o = "\u043e"
        tree = ast.parse("def ertelmezhet" + cirill_o + "():\n    pass\n")
        found = [
            n.name
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and any(_is_confusable(c) for c in n.name)
        ]
        self.assertEqual(len(found), 1, "a homoglif-kapu nem fog")

    def test_a_kapu_atengedi_a_MAGYAR_ekezeteket(self) -> None:
        """A másik irány: a magyar ékezet latin betű, és a repó tele van vele.
        Egy mindig-piros kapu ugyanolyan haszontalan, mint egy mindig zöld."""
        tree = ast.parse("def test_mertekegyseg_orzese_hosszu():\n    pass\n")
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.assertFalse([c for c in node.name if _is_confusable(c)])
        for ch in "őűáéíóúüö":
            with self.subTest(ch=ch):
                self.assertFalse(_is_confusable(ch), f"{ch!r} latin, nem lehet talalat")


class NoDynamicEvaluationTests(unittest.TestCase):
    """A prototípus kiértékelte a képleteket; mi ezt kimondottan NEM vettük át."""

    FORBIDDEN = {"eval", "exec", "compile"}

    def test_nincs_eval_exec_compile_a_csomagban(self) -> None:
        offenders: list[str] = []
        for path in sorted((REPO / "src").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in self.FORBIDDEN
                ):
                    offenders.append(
                        f"{path.relative_to(REPO).as_posix()}:{node.lineno} {node.func.id}"
                    )
        self.assertEqual(
            offenders,
            [],
            "dinamikus kiertekeles a csomagban: "
            + "; ".join(offenders)
            + ". A szamtan ZART muvelet-keszlettel megy (Operation), nem kifejezes-nyelvvel.",
        )

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        tree = ast.parse("x = eval('1+1')\n")
        found = [
            n.func.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in self.FORBIDDEN
        ]
        self.assertEqual(found, ["eval"])


class NoAbsolutePathTests(unittest.TestCase):
    """Abszolút útvonal a forrásban — a repó PUBLIKUS."""

    # A szeparator utan VALODI nev-karakter kell allnia. Ezt egy bukó teszt
    # kerte: az elso valtozat a naplo-modul SZEMLELTETO kommentjere is
    # illeszkedett (egy meghajto-betus helyorzo). A kommenteket NEM vettem ki a
    # meresbol -- ott is lehet igazi szivargas --, hanem a mintat pontositottam:
    # egy helyorzo (harom pont) nem utvonal, egy valodi konyvtarnev igen.
    PATTERN = re.compile(
        r"""['"](?:[A-Za-z]:[\\/][A-Za-z0-9_]|/(?:home|Users|opt|var|mnt)/[A-Za-z0-9_])"""
    )

    # A teszt-fajlok szandekosan hasznalnak PELDA abszolut utakat a kapuk
    # meresehez. Ezek nem szivargasok -- de a kivetel-listat KIMONDJUK, es a
    # letezeset is merjuk: egy elavult kivetel csendben kihagyna egy fajlt.
    ALLOWED = ("tests/test_observability.py", "tests/test_source_hygiene.py")

    def test_nincs_abszolut_ut_a_forrasban(self) -> None:
        offenders: list[str] = []
        for path in _python_files():
            rel = path.relative_to(REPO).as_posix()
            if rel in self.ALLOWED:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if self.PATTERN.search(line):
                    offenders.append(f"{rel}:{lineno}")
        self.assertEqual(
            offenders,
            [],
            "abszolut utvonal a forrasban (a repo PUBLIKUS): " + "; ".join(offenders),
        )

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        minta = [
            "p = " + chr(34) + "C:/Users/valaki/f.csv" + chr(34),
            "p = " + chr(34) + "/home/valaki/f.csv" + chr(34),
            "p = " + chr(34) + "/opt/app/config.json" + chr(34),
        ]
        for sor in minta:
            with self.subTest(sor=sor):
                self.assertTrue(self.PATTERN.search(sor), "nem fog: " + sor)

    def test_a_kapu_atengedi_a_RELATIV_utat(self) -> None:
        minta = [
            "p = " + chr(34) + "profiles/job-sheet.json" + chr(34),
            "p = " + chr(34) + "src/doccapture" + chr(34),
            "p = " + chr(34) + "arlista.csv" + chr(34),
            "sep = " + chr(34) + "/" + chr(34),
            # SZEMLELTETO helyorzo egy kommentben -- nem utvonal. Ezt az esetet
            # egy bukó teszt hozta elo a naplo-modulban, es ezert kerult ide.
            "# meghajto: " + chr(34) + "C:" + chr(92) + "..." + chr(34),
            "# vagy " + chr(34) + "C:/..." + chr(34),
        ]
        for sor in minta:
            with self.subTest(sor=sor):
                self.assertIsNone(self.PATTERN.search(sor), "hamis pozitiv: " + sor)

    def test_a_kivetel_lista_MINDEN_eleme_letezik(self) -> None:
        """Egy elavult kivétel csendben kihagyna egy fájlt a mérésből."""
        for rel in self.ALLOWED:
            with self.subTest(rel=rel):
                self.assertTrue((REPO / rel).is_file(), "elavult kivetel: " + rel)


if __name__ == "__main__":
    unittest.main()
