"""A szállított bináris artefaktumok kapuja — a repó PUBLIKUS, és a G5 érvényes rá.

MIÉRT VAN EGYÁLTALÁN ILYEN TESZT
--------------------------------
Két, egymástól független rés zárul be itt, és **mindkettőt mérés hozta elő**:

1. **Bináris-oldalon nem volt SEMMILYEN kapu.** A saját szabályunk kimondja,
   hogy *üzleti bináris SOSEM kerül a repóba* — de a `.gitignore` csak néhány
   konkrét kiterjesztést tilt (`*.pdf`, `*.xlsx`, `*.jpg`, `*.png`). Ez
   **felsorolás, nem szabály**: egy `.ttf`, `.zip`, `.dll` vagy egy átnevezett
   üzleti minta **csendben bemegy** egy publikus repóba.

   ⚠ Ezt egy **saját, pontatlan állításom** hozta elő: azt jelentettem, hogy „a
   `.gitignore` binárist tilt, tehát szűk kivétel kell". Megmérve **nem tilt** —
   vagyis nem kivételt kellett adni, hanem a **hiányzó kaput megépíteni**. A
   kettő ellentétes irányú munka.

2. **A licenc-kapu (G5) csak pip-csomagokat lát.** Egy szállított *nem-pip*
   artefaktum licence — mint a beágyazott betűtípusé — **mérés nélkül** maradna:
   a `LICENSE` fájl ott lehet a repóban, a G5-öt őrző gépi kapu **akkor sem tud
   róla**. A manifeszt ezt zárja be.

A LEGFONTOSABB MÉRÉS EBBEN A FÁJLBAN
------------------------------------
`test_a_betutipus_FEDI_a_magyar_keszletet`: nem azt méri, hogy a fájl **ott
van-e**, hanem hogy **használható-e**. Mérve (DC-01 terv): ugyanaz a hibás PDF
két olvasóval **három különböző hibaalakot** ad, és a beépített Helvetica az
egyik olvasón **helyes hosszúságú** szöveget ad, csak a karakter `■`. Vagyis egy
hossz- vagy „tiltott karakter" alapú ellenőrzés **üresen zöld**. És a hiba
**láthatatlan szövegrétegben** van — szemmel soha nem derül ki.
"""

from __future__ import annotations

import json
import sys
import unittest
from importlib import resources
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import binary_guard as guard  # noqa: E402

MANIFEST = json.loads((REPO / "tools" / "binary_artifacts.json").read_text(encoding="utf-8"))
FONT = REPO / "src" / "doccapture" / "resources" / "LiberationSans-Regular.ttf"


class ManifestTests(unittest.TestCase):
    """A deklaráció és a valóság EGYEZIK — két igazság ugyanarról a leggyakoribb hibánk."""

    def test_a_kapu_TISZTA_a_valodi_repon(self) -> None:
        """Ez a mérés, amit a CI is futtat."""
        problems = guard.check(REPO, MANIFEST)
        self.assertEqual(problems, [], "a binaris-kapu elbukott:\n  " + "\n  ".join(problems))

    def test_minden_deklaralt_artefaktum_LETEZIK_es_a_hash_EGYEZIK(self) -> None:
        for entry in MANIFEST["artifacts"]:
            with self.subTest(path=entry["path"]):
                path = REPO / entry["path"]
                self.assertTrue(path.is_file(), "deklaralt, de hianyzo artefaktum")
                self.assertEqual(guard.sha256_of(path), entry["sha256"])

    def test_minden_artefaktumnak_van_LICENC_fajlja_es_EREDETE(self) -> None:
        """Egy licenc nélküli bináris egy MIT-ként terjesztett csomagban jogi
        probléma; egy eredet nélküli bináris pedig visszakövethetetlen."""
        for entry in MANIFEST["artifacts"]:
            with self.subTest(path=entry["path"]):
                self.assertTrue((REPO / entry["license_file"]).is_file())
                for kulcs in ("license", "origin_project", "origin_release", "origin_url"):
                    self.assertTrue(entry.get(kulcs), f"hianyzo mezo: {kulcs}")

    def test_a_kapu_HARAP_NEM_DEKLARALT_binarison(self) -> None:
        """Negatív kontroll a manifeszt-oldalon: egy üres deklarációval a repóban
        lévő betűtípusnak **el kell buknia**. Enélkül nem tudnánk, hogy a kapu
        azért zöld, mert minden deklarált — vagy mert sosem néz semmit."""
        ures = {"artifacts": []}
        problems = guard.check(REPO, ures)
        self.assertTrue(problems, "a kapu ures deklaracioval is zold — nem mer semmit")
        self.assertTrue(
            any("NEM DEKLARALT" in line for line in problems),
            f"nem a vart okbol bukott: {problems}",
        )

    def test_a_kapu_HARAP_ELROMLOTT_hash_eseten(self) -> None:
        """Egy kicserélt betűtípus a terméket **némán** rontaná el."""
        romlott = json.loads(json.dumps(MANIFEST))
        romlott["artifacts"][0]["sha256"] = "0" * 64
        problems = guard.check(REPO, romlott)
        self.assertTrue(
            any("sha256 NEM egyezik" in line for line in problems),
            f"a hash-eltérést nem jelezte: {problems}",
        )


class GateWiringTests(unittest.TestCase):
    """A `check()` TÉNYLEG felhasználja-e a méréseket, amiket elvégez.

    ⚠ **Ezt az osztályt egy ÁTMENT MUTÁCIÓ hozta létre, és a lelet a tesztjeimről
    szólt.** A `FontUsabilityTests` a `font_report()`-ot **közvetlenül** hívja,
    tehát a mérés helyességét bizonyítja — azt **nem**, hogy a kapu az eredményt
    **fel is használja**. A mutáció (`if report["missing"]:` → `if False:`)
    **átment**: a `check()` glyph-ágát semmi nem őrizte.

    Ez ugyanaz az alak, mint a „két réteg fedi egymást, és a kiesőt viselkedésben
    nem látni": a mérés és a **döntés** két külön dolog, és **külön kell mérni**.
    """

    def _with_charset(self, charset: str):
        """A megkövetelt készlet ideiglenes cseréje — a valódi kód-úton."""
        eredeti = guard.REQUIRED_CHARSET
        guard.REQUIRED_CHARSET = charset
        self.addCleanup(lambda: setattr(guard, "REQUIRED_CHARSET", eredeti))

    def test_a_check_ELBUKIK_ha_a_betutipus_NEM_fedi_a_keszletet(self) -> None:
        """A kapu **döntése** mérve, nem csak a mérése."""
        self._with_charset(guard.HUNGARIAN_CHARSET + "中")
        problems = guard.check(REPO, MANIFEST)
        self.assertTrue(
            any("NEM fedi a megkovetelt keszletet" in line for line in problems),
            f"a check() a fedes-hianyt NEM jelezte: {problems}",
        )

    def test_a_check_ELBUKIK_ha_a_POZITIV_kontroll_elszall(self) -> None:
        """Ha a mérőeszköz olyat is megtalál, aminek nem szabadna ott lennie, a
        mérés **érvénytelen** — és ezt a kapunak ki kell mondania."""
        eredeti = guard.ABSENT_CONTROL
        guard.ABSENT_CONTROL = "a"  # ez BIZTOSAN benne van a fontban
        self.addCleanup(lambda: setattr(guard, "ABSENT_CONTROL", eredeti))
        problems = guard.check(REPO, MANIFEST)
        self.assertTrue(
            any("POZITIV KONTROLL elbukott" in line for line in problems),
            f"a check() az ervenytelen merest NEM jelezte: {problems}",
        )

    def test_a_check_ELBUKIK_a_DEKLARALT_de_HIANYZO_artefaktumon(self) -> None:
        hamis = json.loads(json.dumps(MANIFEST))
        hamis["artifacts"][0]["path"] = "src/doccapture/resources/nincs-ilyen.ttf"
        problems = guard.check(REPO, hamis)
        self.assertTrue(
            any("HIANYZO artefaktum" in line for line in problems),
            f"a hianyzo artefaktumot nem jelezte: {problems}",
        )

    def test_a_check_ELBUKIK_ha_a_LICENC_fajl_hianyzik(self) -> None:
        """Az OFL a licenc továbbadását **kötelezővé** teszi — ha a fájl eltűnik,
        az nem szépséghiba."""
        hamis = json.loads(json.dumps(MANIFEST))
        hamis["artifacts"][0]["license_file"] = "src/doccapture/resources/nincs-licenc.txt"
        problems = guard.check(REPO, hamis)
        self.assertTrue(
            any("licenc-fajl HIANYZIK" in line for line in problems),
            f"a hianyzo licencet nem jelezte: {problems}",
        )


class FontUsabilityTests(unittest.TestCase):
    """A betűtípus HASZNÁLHATÓ-e — nem az, hogy ott van-e."""

    def test_a_betutipus_FEDI_a_magyar_keszletet(self) -> None:
        report = guard.font_report(FONT, charset=guard.HUNGARIAN_CHARSET)
        self.assertEqual(
            report["missing"],
            [],
            "a betutipus NEM fedi a magyar keszletet: " + "".join(report["missing"]),
        )

    def test_a_HOSSZU_ekezet_kulon_merve(self) -> None:
        """Ez az a négy karakter, ami a beépített betűtípusoknál elesik — és
        éppen ezek miatt kell egyáltalán beágyazott font."""
        report = guard.font_report(FONT, charset="őűŐŰ")
        self.assertEqual(report["missing"], [], "a hosszu ekezet HIANYZIK a betutipusbol")

    def test_a_meres_POZITIV_kontrollja(self) -> None:
        """⚠ Enélkül a „minden karakter megvan" válasz jelenthetné azt is, hogy a
        cmap-olvasóm mindig nem-nullát ad. A CJK-készletnek **hiányoznia kell**."""
        report = guard.font_report(FONT, charset="中ア")
        self.assertEqual(
            sorted(report["missing"]),
            sorted("中ア"),
            "a glyph-meres CJK-t is fedettnek mond — a meres ERVENYTELEN",
        )

    def test_a_betutipus_BEAGYAZHATO(self) -> None:
        """OFL ide vagy oda: a betűtípus **saját** `fsType` bitje is tilthatja a
        beágyazást, és akkor kereshető PDF-be nem tehető."""
        report = guard.font_report(FONT)
        self.assertTrue(
            report["embeddable"],
            f"a beagyazas TILTOTT (fsType={report['fs_type']})",
        )

    def test_a_megkovetelt_keszlet_NEM_URES(self) -> None:
        """Egy üres készleten minden betűtípus átmenne — üresen zöld kapu."""
        self.assertGreater(len(set(guard.REQUIRED_CHARSET)), 60)
        for char in "őűáéíóöúü":
            with self.subTest(char=char):
                self.assertIn(char, guard.REQUIRED_CHARSET)


class ShippingTests(unittest.TestCase):
    """A betűtípus eljut-e a FOGYASZTÓHOZ — a repóban állni nem elég."""

    def test_a_betutipus_IMPORTLIB_RESOURCES_szel_elerheto(self) -> None:
        """Ez a runtime-elérés útja, és **környezet-független**: forrásfából és
        telepített csomagból is ugyanígy old fel.

        ⚠ Szándékosan NEM `__file__`-alapú útépítés: az zip-importnál és
        szerkeszthető telepítésnél elszáll, és a hibája **telepítés-függő** lenne.
        """
        from doccapture import resources as res

        fajl = resources.files(res).joinpath(res.EMBEDDED_FONT_FILENAME)
        self.assertTrue(fajl.is_file(), "a betutipus nem erheto el a csomagbol")
        self.assertGreater(len(fajl.read_bytes()), 100_000)

        licenc = resources.files(res).joinpath(res.EMBEDDED_FONT_LICENSE_FILENAME)
        self.assertTrue(licenc.is_file(), "a licenc nem erheto el a csomagbol")

    def test_a_pyproject_KIMONDVA_szallitja_az_eroforrasokat(self) -> None:
        """A csomagolási szabály **deklaratív** kérdés — ha kiesik, a fájl a
        repóban marad, a telepített csomagból viszont eltűnik, és ezt semmilyen
        futásidejű teszt nem venné észre a fejlesztői gépen (ott a forrásfa van
        a `sys.path`-on)."""
        import tomllib

        data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = data["tool"]["setuptools"]["package-data"]
        minta = package_data["doccapture.resources"]
        self.assertIn("*.ttf", minta)
        self.assertTrue(
            any(m.startswith("LICENSE-") for m in minta),
            "az OFL TOVABBADASA kotelezettseg -- a licenc-fajlnak szallitodnia kell",
        )

    def test_a_nev_EGY_helyen_all(self) -> None:
        """A fájlnév a manifesztben és a csomagban is szerepel — ha elcsúsznak,
        a kapu mást mér, mint amit a kód betölt."""
        from doccapture import resources as res

        deklaralt = {Path(e["path"]).name for e in MANIFEST["artifacts"]}
        self.assertIn(res.EMBEDDED_FONT_FILENAME, deklaralt)
        self.assertIn(res.EMBEDDED_FONT_LICENSE_FILENAME, deklaralt)


if __name__ == "__main__":
    unittest.main()
