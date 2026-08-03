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


# A repoban PUBLIKALT szovegfajlok. A `.py` szandekosan benne van: a
# felhasznalo-azonosito ut ott is szivargas, nem csak dokumentacioban.
PUBLISHED_SUFFIXES = {".py", ".md", ".json", ".toml", ".yaml", ".yml", ".cfg", ".txt"}
SKIPPED_PARTS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


def _published_text_files() -> list[Path]:
    """Minden publikált szövegfájl a repóban — nem csak a `src/tests/tools` `.py`-jai."""
    files: list[Path] = []
    for path in sorted(REPO.rglob("*")):
        if not path.is_file() or path.suffix not in PUBLISHED_SUFFIXES:
            continue
        if any(part in SKIPPED_PARTS for part in path.parts):
            continue
        files.append(path)
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


class NoUserIdentifyingPathTests(unittest.TestCase):
    """FELHASZNÁLÓ-AZONOSÍTÓ útvonal — bárhol, bármilyen elválasztóval.

    ⚠ **Ezt a kaput egy MÉRT rés hozta létre, a DC-01b előmunkálataként.** A
    `NoAbsolutePathTests` (fentebb) a saját indoklása szerint azért létezik, mert
    *„a repó PUBLIKUS"* — de **csak `*.py`-t olvas**, és **idézőjelet követel** a
    minta elé. A DC-01 terve azt írta, hogy a betűtípus-proveniencia `.md`-be
    írása „megbuktatná" ezt a kaput; **megmérve az állítás nem áll** — a kapu a
    `.md`-t **el sem olvassa**. A terv aggálya tehát nem ütközés volt, hanem
    **rés**, csak rossz helyen keresve.

    Három vakfolt, mérve — és mindhármat pont a font-dokumentáció alakja találja el:

    | alak | a régi minta |
    |---|---|
    | `font = "C:/Windows/Fonts/arial.ttf"` (idézőjel) | fog |
    | `` `C:\\Users\\valaki\\f.txt` `` (backtick — a markdown írásmódja) | **NEM fog** |
    | `/usr/share/fonts/...` (nincs az előtag-listán) | **NEM fog** |
    | csupasz út elválasztó nélkül | **NEM fog** |

    Vagyis pusztán a fájlkör bővítése **üresen zöld** kaput adott volna: 0 találat,
    miközben a valódi szivárgás-alak átmegy.

    MIT MÉR EZ A KAPU, ÉS MIT SZÁNDÉKOSAN NEM
    -----------------------------------------
    A kérdés nem az, hogy „abszolút-e az út", hanem hogy **elárul-e valamit egy
    konkrét gépről vagy emberről**:

    - `C:/Users/<valaki>/...`, `/home/<valaki>/...` → **szivárgás**, tiltott;
    - `C:/Windows/Fonts/arial.ttf`, `/usr/share/fonts/...` → **nem szivárgás**:
      minden gépen ugyanaz, semmit nem árul el. És a **betűtípus-politikának
      dokumentálnia KELL** őket (melyik rendszer-font EULA-s) — egy kapu, ami ezt
      tiltaná, a helyes dokumentációt akadályozná.

    ⚠ Ez a kapu **nem gyengíti** a `NoAbsolutePathTests`-t: az változatlanul
    szigorú marad a `.py`-kra (kódban abszolút út mindig hiba, ld. QUALITY §3).
    Ez a réteg **hozzáad**: más fájlkört és más elválasztó-készletet mér.
    """

    # Elvalaszto-FUGGETLEN: nincs benne idezojel-kikotes, mert a markdown
    # backtickkel ir utat, a tablazat-cellak pedig sehogy.
    PATTERN = re.compile(r"(?:[A-Za-z]:[\\/])?(?:Users|home)[\\/]([A-Za-z0-9_.-]+)")

    # Ugyanaz a kivetel-lista, mint a `NoAbsolutePathTests`-nel, ugyanabbol az
    # okbol: ezek a fajlok SZANDEKOSAN tartalmaznak pelda-utakat a kapuk
    # meresehez. A letezesuket kulon teszt meri -- egy elavult kivetel csendben
    # kihagyna egy fajlt.
    #
    # ⚠ A `tools/mutations.json` **a sajat kapu-epites kozben** kerult ide, es a
    # tanulsag altalanos: a mutacios config LITERALIS proba-ertekeket tart, tehat
    # egy szivargas-kaput dokumentalo fajl maga is **uj talalatot gyart**. Nem
    # blanketta-kivetelt adtunk neki, hanem SZUKEBB szabalyt: ott csak ismert
    # helyorzo-nev allhat (ld. `test_a_mutacios_config_csak_HELYORZO_nevet_tarthat`).
    ALLOWED = (
        "tests/test_observability.py",
        "tests/test_source_hygiene.py",
        "tools/mutations.json",
    )

    # A repo bevalt helyorzoi. Egy VALODI felhasznalonev ezek kozott nem szerepel,
    # tehat a szukebb szabaly a kivetelezett fajlban is fog.
    PROBE_NAMES = frozenset({"valaki"})

    def test_nincs_felhasznalo_azonosito_ut_egyetlen_publikalt_fajlban_sem(self) -> None:
        offenders: list[str] = []
        for path in _published_text_files():
            rel = path.relative_to(REPO).as_posix()
            if rel in self.ALLOWED:
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                match = self.PATTERN.search(line)
                if match:
                    offenders.append(f"{rel}:{lineno} (felhasznalo-nev: {match.group(1)!r})")
        self.assertEqual(
            offenders,
            [],
            "felhasznalo-azonosito utvonal egy PUBLIKUS repoban: " + "; ".join(offenders),
        )

    def test_a_kapu_HARAP_MINDEN_elvalaszto_alakon(self) -> None:
        """A három vakfolt, amit a régi minta átengedett — most mind fogni kell."""
        user_win = "C:" + chr(92) + "Users" + chr(92) + "gabor" + chr(92) + "f.txt"
        minta = [
            ("idezojeles", "p = " + chr(34) + "C:/Users/gabor/f.txt" + chr(34)),
            ("BACKTICKES (markdown)", "forras: `" + user_win + "`"),
            ("tablazat-cella", "| `" + user_win + "` | EULA |"),
            ("csupasz, elvalaszto nelkul", "A fajl itt van: /home/gabor/adat.csv"),
            ("md-link", "[a fajl](file:///home/gabor/adat.csv)"),
        ]
        for nev, sor in minta:
            with self.subTest(alak=nev):
                self.assertTrue(self.PATTERN.search(sor), "nem fog: " + nev)

    def test_a_kapu_ATENGEDI_az_altalanos_RENDSZER_utat(self) -> None:
        """A másik irány, és ez a **termék** szempontjából fontos.

        A betűtípus-politikának ki kell mondania, melyik rendszer-font EULA-s és
        melyik szabad. Ezek az utak **minden gépen ugyanazok**, tehát semmit nem
        árulnak el — egy mindig-piros kapu itt a helyes dokumentációt tiltaná be.
        """
        minta = [
            "| `C:" + chr(92) + "Windows" + chr(92) + "Fonts" + chr(92) + "arial.ttf` | Monotype EULA |",
            "forras: `/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf`",
            "a rendszer font-mappaja: C:/Windows/Fonts/",
            "beagyazott betutipus: fonts/LiberationSans-Regular.ttf",
        ]
        for sor in minta:
            with self.subTest(sor=sor):
                self.assertIsNone(self.PATTERN.search(sor), "hamis pozitiv: " + sor)

    def test_a_meres_a_MARKDOWN_fajlokra_IS_kiterjed(self) -> None:
        """⚠ Enélkül a kapu **üresen zöld** lenne: a régi réteg csak `*.py`-t
        olvasott, és pont a `.md` a hely, ahova a proveniencia kerül."""
        suffixes = {path.suffix for path in _published_text_files()}
        for kell in (".md", ".py", ".json"):
            with self.subTest(suffix=kell):
                self.assertIn(kell, suffixes, f"a meres NEM olvas {kell} fajlt")

        # A README minden repoban van -- ha a bejaro nem talalja meg, a
        # "0 talalat" a bejarasrol szol, nem a repo tisztasagarol.
        nevek = {path.name for path in _published_text_files()}
        self.assertIn("README.md", nevek, "a bejaro a README.md-t sem latja")

    def test_a_kivetel_lista_MINDEN_eleme_letezik(self) -> None:
        """Egy elavult kivétel csendben kihagyna egy fájlt a mérésből."""
        for rel in self.ALLOWED:
            with self.subTest(rel=rel):
                self.assertTrue((REPO / rel).is_file(), "elavult kivetel: " + rel)

    def test_a_mutacios_config_csak_HELYORZO_nevet_tarthat(self) -> None:
        """A kivétel **nem blanketta** — a mutációs config szigorúbb szabály alá esik.

        ⚠ Ez a teszt egy **saját, mért hibából** született: a két új
        higiénia-mutáció felvételekor a `tools/mutations.json`-ba valódi
        alakú próba-utak kerültek, és **a saját kapum buktatta el a saját
        alapállapotát** (`ERVENYTELEN` mérés, „az alapallapot mar piros").

        Egy szivárgás-kaput dokumentáló fájl **maga is új találatot gyárt** — a
        helyes válasz nem a kapu tágítása és nem is blanketta-kivétel, hanem
        **szűkebb szabály**: itt csak ismert helyőrző-név állhat.
        """
        path = REPO / "tools" / "mutations.json"
        rossz: list[str] = []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in self.PATTERN.finditer(line):
                if match.group(1) not in self.PROBE_NAMES:
                    rossz.append(f"tools/mutations.json:{lineno} -> {match.group(1)!r}")
        self.assertEqual(
            rossz,
            [],
            "NEM helyorzo nev a mutacios configban (a kivetel nem blanketta): "
            + "; ".join(rossz),
        )

    def test_a_SZUKEBB_szabaly_HARAP_negativ_kontroll(self) -> None:
        """A szűkebb szabály fogna egy valódi felhasználónevet is."""
        sor = "  " + chr(34) + "replace" + chr(34) + ": " + chr(34) + "C:/Users/szanto/x" + chr(34)
        talalat = [m.group(1) for m in self.PATTERN.finditer(sor)]
        self.assertEqual(talalat, ["szanto"])
        self.assertNotIn("szanto", self.PROBE_NAMES, "a negativ kontroll nem allit semmit")


if __name__ == "__main__":
    unittest.main()
