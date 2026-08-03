"""A licenc-kapu tesztjei — a G5 szabály MÉRVE, nem kimondva.

MIÉRT VAN EGYÁLTALÁN ILYEN TESZT
--------------------------------
A **G5** döntés MIT licencet ír elő, és a DC-01 felderítése kimérte, hogy ezt
**semmilyen gépi kapu nem őrizte**: a motor `tools/` mappájában nem volt
licenc-ellenőrző, tehát *„az első DC-01 függőséggel a szabály azonnal mérés
nélkülivé válik — GPL-függőséggel is lefordul és zöld a suite."*

A LEGÉRTÉKESEBB TESZT EBBEN A FÁJLBAN
-------------------------------------
`test_a_kapu_ELBUKTAT_MINDEN_copyleft_licenc_alakot`: nem kitalált licenc-szöveget
osztályoz, hanem **valódi csomagokból rögzített** metaadat-alakokat deklarál egy
eldobható `pyproject.toml`-ban, és megméri, hogy a kapu elbukik rajtuk. Egy
szöveg-osztályozó teszt csak azt bizonyítja, hogy a *szabálylista* helyes; ez
azt, hogy a **kapu össze is áll**.

⚠ **A FÁJL KÉT MÉRÉSE KORÁBBAN A GÉPTŐL FÜGGÖTT, ÉS EMIATT VOLT PIROS A CI.**
Mindkettő a fejlesztői gépen *véletlenül* telepített csomagokra épült:

| Mérés | Amire épült | Tünete tiszta gépen |
|---|---|---|
| zárvány-bejárás | telepített `reportlab` | **bukás** (`hamis 'nem mertem'`) |
| copyleft-elbuktatás | bármely telepített GPL-es csomag | **számolt kihagyás** |

Mindkettő ugyanaz az osztály: *a kapu olyan gépen készült, ahol minden telepítve
van.* A javítás is közös — a mintát **magunkkal visszük**
(`tests/requirement_shapes.py`, valódi metaadatból gépileg rögzítve), így a
mérés minden gépen ugyanazt méri.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import license_guard as guard  # noqa: E402

sys.path.insert(0, str(REPO / "tests"))

import requirement_shapes as shapes  # noqa: E402

CONFIG = REPO / "tools" / "licenses.json"


def _license_specimen_sources() -> set[str]:
    """A licenc-minták metaadat-mezőinek KULCSAI — melyik forrást fedik le.

    A `license_of` három helyről olvas (`License-Expression` → `Classifier` →
    `License`). Ha a minta-készlet csak egyet fedne, a visszalépési lánc többi
    ága **mérés nélkül** maradna.
    """
    return {
        key
        for specimen in shapes.LICENSE_SPECIMENS.values()
        for key, _value in specimen["mezok"]
    }


class SelfTestTests(unittest.TestCase):
    """A kapu öntesztje ZÖLD — enélkül a kapu eredménye nem értelmezhető."""

    def test_az_onteszt_atmegy(self) -> None:
        proc = subprocess.run(
            [sys.executable, "tools/license_guard.py", "--selftest"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("harap es nem vaklarma", proc.stdout)


class ClassificationTests(unittest.TestCase):
    """A szabálylista precedenciája — a tiltás nyer, ha mindkettőre illeszkedik."""

    def setUp(self) -> None:
        self.config = guard.json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_a_DUAL_licenc_TILTOTT_nem_megengedett(self) -> None:
        """Az AGPL-es dual-licenc tiltott (pl. a PyMuPDF `Dual Licensed - GNU AFFERO`)."""
        self.assertEqual(
            guard.classify("Dual Licensed - GNU AFFERO GPL 3.0 or commercial", self.config),
            "tiltott",
        )

    def test_a_PRECEDENCIA_merve_MINDKET_listara_illeszkedo_szovegen(self) -> None:
        """⚠ Ezt a tesztet egy ÁTMENT mutáció hozta létre, és a lelet a tesztről szólt.

        Az első „precedencia-tesztem" a `Dual Licensed - GNU AFFERO / commercial`
        szöveget osztályozta — de **mérve**: az egyetlen megengedő mintára sem
        illeszkedik, tehát a lista-sorrend nála **nem is számít**. Amit
        precedencia-tesztnek hívtam, nem az volt: a tiltást bizonyította, a
        sorrendet nem.

        A precedencia CSAK olyan szövegen mérhető, ami **mindkét listára** illik.
        Ez nem elméleti eset: a valódi dual-licencek gyakran ilyenek
        (`Apache-2.0 OR GPL-3.0`), és ott a **tiltás kell hogy nyerjen** —
        különben egy copyleft-opciós csomag csendben átmegy.
        """
        for text in (
            "Apache-2.0 OR GPL-3.0-only",
            "MIT OR GPL-2.0-or-later",
            "BSD-3-Clause OR LGPL-2.1",
            "MPL-2.0 OR Apache-2.0 OR GPL-2.0",
        ):
            with self.subTest(text=text):
                low = text.lower()
                # A meres ELOFELTETELE: a szoveg tenyleg mindkét listara illik.
                self.assertTrue(
                    any(p.lower() in low for p in self.config["denied"]),
                    "a proba-szoveg nem illeszkedik a tilto listara",
                )
                self.assertTrue(
                    any(p.lower() in low for p in self.config["allowed"]),
                    "a proba-szoveg nem illeszkedik a megengedo listara — "
                    "igy NEM meri a precedenciat",
                )
                self.assertEqual(guard.classify(text, self.config), "tiltott")

    def test_a_csak_SZOKOZ_licenc_NEM_MERHETO_nem_ismeretlen(self) -> None:
        """⚠ Ezt a saját önteszt hozta elő. A két állapot MÁS javítást kér: a
        'nem tudtuk megmérni' kézi feloldást, a 'nem ismerjük fel' döntést a
        szabálylistáról. Összemosva a fejlesztő a rossz helyen keresne."""
        self.assertEqual(guard.classify("   ", self.config), "nem-merheto")
        self.assertEqual(guard.classify("", self.config), "nem-merheto")

    def test_az_MPL_SZANDEKOSAN_fel_nem_ismert(self) -> None:
        """Fájl-szintű copyleft: MIT-terjesztésnél nem triviális. A kapu ezért
        elbuktatja, és a döntés KIMONDOTT lesz — nem csendben megengedett."""
        self.assertEqual(guard.classify("MPL-2.0", self.config), "ismeretlen")

    def test_a_megengedett_alakok_atmennek(self) -> None:
        for text in ("MIT", "MIT-CMU", "BSD-3-Clause", "Apache-2.0", "ISC"):
            with self.subTest(text=text):
                self.assertEqual(guard.classify(text, self.config), "megengedett")


class VersionFloorTests(unittest.TestCase):
    """A licenc a VERZIÓ tulajdonsága — a surya-tanulság.

    Mérve: `surya-ocr` 0.1.0…0.19.x = GPL-3.0-or-later, 0.20.0-tól Apache-2.0.
    A helyes szabály nem „tilos", hanem „0.20.0 alatt tilos" — és ezt a
    `pyproject` alsó korlátjának kell kikényszerítenie.
    """

    def setUp(self) -> None:
        self.config = guard.json.loads(CONFIG.read_text(encoding="utf-8"))

    def test_a_KORLAT_NELKULI_hivatkozas_elbukik(self) -> None:
        problems = guard.check_version_floors(self.config, {"surya-ocr": "surya-ocr"})
        self.assertEqual(len(problems), 1)
        self.assertIn("NEM ir elo als", problems[0])

    def test_a_TUL_ALACSONY_korlat_elbukik(self) -> None:
        problems = guard.check_version_floors(self.config, {"surya-ocr": "surya-ocr>=0.17.1"})
        self.assertEqual(len(problems), 1)
        self.assertIn("ALACSONYABB", problems[0])

    def test_az_ELEG_HAGY_korlat_atmegy(self) -> None:
        """A másik irány: egy mindig-buktató szabály használhatatlan."""
        for line in ("surya-ocr>=0.20.0", "surya-ocr>=0.22.1", "surya-ocr >= 1.0"):
            with self.subTest(line=line):
                self.assertEqual(guard.check_version_floors(self.config, {"surya-ocr": line}), [])

    def test_amire_NEM_hivatkozunk_azt_nem_vizsgalja(self) -> None:
        """Egy nem használt csomag korlátja nem hiba — különben a szabálylista
        bővítése elbuktatná a kaput olyan csomagon, amit nem is használunk."""
        self.assertEqual(guard.check_version_floors(self.config, {}), [])

    def test_a_verzio_osszehasonlitas_szamszerint_megy_nem_szoveg_szerint(self) -> None:
        """`0.9.0` NEM nagyobb, mint `0.20.0` — szöveg-összehasonlítással az lenne."""
        self.assertLess(guard.parse_version("0.9.0"), guard.parse_version("0.20.0"))
        self.assertLess(guard.parse_version("0.19.9"), guard.parse_version("0.20.0"))
        self.assertGreater(guard.parse_version("0.22.1"), guard.parse_version("0.20.0"))


class EndToEndTests(unittest.TestCase):
    """A kapu ÖSSZEÁLL-e — eldobható repó-gyökéren mérve."""

    def _run(self, pyproject: str, specimen_path: Path | None = None) -> subprocess.CompletedProcess:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        Path(tmp.name, "pyproject.toml").write_text(pyproject, encoding="utf-8")

        # ⚠ A kapu ALPROCESSZBEN fut, tehat a hivo `sys.path`-jat NEM orokli --
        # eppen ez a mechanizmus buktatta a CI-t (root-lelet, 5. ok). A minta
        # ezert `PYTHONPATH`-on megy at, kimondva.
        env = None
        if specimen_path is not None:
            env = dict(os.environ)
            env["PYTHONPATH"] = str(specimen_path)

        return subprocess.run(
            [
                sys.executable,
                str(REPO / "tools" / "license_guard.py"),
                "--root",
                tmp.name,
                "--config",
                str(CONFIG),
            ],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_a_fuggoseg_NELKULI_projekt_KIMONDOTT_nulla_nem_zold_meres(self) -> None:
        """Egy üresen zöld licenc-kapu pontosan úgy néz ki, mint egy tiszta lánc."""
        proc = self._run('[project]\nname = "proba"\nversion = "0.0.0"\n')
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("KIMONDOTT nulla", proc.stdout)

    def test_egy_MEGENGEDETT_fuggoseg_atmegy(self) -> None:
        proc = self._run(
            '[project]\nname = "proba"\nversion = "0.0.0"\ndependencies = ["openpyxl>=3.1"]\n'
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("TISZTA", proc.stdout)

    def test_a_kapu_ELBUKTAT_MINDEN_copyleft_licenc_alakot(self) -> None:
        """Ez a fájl legértékesebb tesztje: nem kitalált licenc-szöveget osztályoz,
        hanem **valódi csomagokból rögzített** metaadat-alakokat deklarál egy
        eldobható `pyproject.toml`-ban, és megméri, hogy a kapu elbukik rajtuk.

        ⚠ **Ez a teszt korábban `skipUnless`-szel kimaradt egy tiszta gépen.** A
        fejlesztői gépen öt telepített copyleft csomag van, egy friss CI-n
        **nulla** — a teszt tehát ott sosem futott, és mivel a mérési kör
        `KIHAGYVA=0`-t követel, emiatt a kör **piros** volt. Ugyanaz a
        környezet-függő vakság, mint a zárvány-mérésnél, csak a tünete nem bukás,
        hanem számolt kihagyás.

        A rögzített készlet egyben **erősebb** is az eredetinél: az azt vette,
        amelyik először akadt a kezébe (nem determinisztikus, gépenként más), ez
        viszont a `license_of` **mindhárom** forrás-mezőjét lefedi.
        """
        self.assertTrue(shapes.LICENSE_SPECIMENS, "nincs licenc-minta — a meres ures")

        with shapes.installed_specimen() as specimen_path:
            for name, specimen in shapes.LICENSE_SPECIMENS.items():
                with self.subTest(minta=name):
                    proc = self._run(
                        f'[project]\nname = "proba"\nversion = "0.0.0"\n'
                        f'dependencies = ["{name}"]\n',
                        specimen_path=specimen_path,
                    )
                    self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                    self.assertIn("TILTOTT LICENC", proc.stdout)
                    self.assertIn(name, proc.stdout)
                    self.assertIn(specimen["version"], proc.stdout)

    def test_a_licenc_mintak_MINDHAROM_forras_mezot_fedik(self) -> None:
        """Ha a készlet csak egy mezőt fedne, a visszalépési lánc többi ága
        **mérés nélkül** maradna — és pont az a rész buktatna el egy valódi
        csomagot, amelyiket senki nem méri."""
        self.assertEqual(
            _license_specimen_sources(),
            {"License-Expression", "Classifier", "License"},
            "a licenc-minta-keszlet nem fedi a `license_of` mindharom forrasat",
        )

    def test_a_NEM_TELEPITETT_fuggoseg_NEM_rendben(self) -> None:
        """Egy nem mért függőség nem 'rendben' — a hallgatás nem zöld."""
        proc = self._run(
            '[project]\nname = "proba"\nversion = "0.0.0"\n'
            'dependencies = ["ez-a-csomag-remelhetoleg-nem-letezik-2026"]\n'
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("NEM MERT", proc.stdout)

    def test_a_MOTOR_sajat_lanca_TISZTA(self) -> None:
        """A valódi repón: ez a mérés, amit a CI is futtat."""
        proc = subprocess.run(
            [sys.executable, "tools/license_guard.py"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Licenc-kapu: TISZTA", proc.stdout)


class RequirementMarkerTests(unittest.TestCase):
    """A marker-kiértékelés — a kapu használhatóságát eldöntő javítás.

    ⚠ **Ezt egy mért hiba hozta létre, és a hiba téves RIASZTÁS volt, nem téves
    engedélyezés.** Az első változat a marker-feltételt levágta, és a csomag-nevet
    feltétel nélkül a zárványba tette. Mérve a `{reportlab, pypdf, pypdfium2}`
    készleten:

    ```
    javitas ELOTT : 29 megtalalt + 77 "NEM TELEPITETT, tehat NEM MERT" = 106
    javitas UTAN  :  5 megtalalt +  0                                  =   5
    ```

    A 77 között `flit`, `sphinx`, `pytest-*`, `coverage` — egyik sem szállított
    függőség. **A `certifi` (MPL-2.0) is így került be**, egy extra-láncon: a kapu
    látszólagos licenc-problémája a saját hibája volt. A zajos kapu a legrosszabb
    fajta: egy héten belül kikapcsolja valaki, és akkor rosszabbul állunk, mint
    kapu nélkül — mert azt hisszük, hogy van.
    """

    def test_az_EXTRA_feltetelu_kovetelmenyt_NEM_koveti(self) -> None:
        for line in (
            'rl_accel<1.1,>=0.9.0; extra == "accel"',
            'sphinx; extra == "docs"',
            'pytest>=8; extra == "test"',
        ):
            with self.subTest(line=line):
                self.assertFalse(guard._runtime_requirement(line))

    def test_a_FELTETEL_NELKULI_kovetelmenyt_koveti(self) -> None:
        """A másik irány: egy mindent kizáró bejáró vakon zöld kaput adna."""
        for line in ("pillow>=9.0.0", "charset-normalizer", "et-xmlfile"):
            with self.subTest(line=line):
                self.assertTrue(guard._runtime_requirement(line))

    def test_a_KORNYEZETI_markert_a_valos_kornyezeten_ertekeli(self) -> None:
        """A `python_version` feltétel nem extra: azt ki KELL értékelni."""
        self.assertTrue(guard._runtime_requirement('typing-extensions; python_version < "4.0"'))
        self.assertFalse(guard._runtime_requirement('typing-extensions; python_version < "3.0"'))

    def test_az_ERTELMEZHETETLEN_sor_nem_kerul_a_zarvanyba(self) -> None:
        """Nem találgatunk — de nem is szállunk el egy hibás metaadaton."""
        self.assertFalse(guard._runtime_requirement("ez nem egy ervenyes requirement ==="))

    def test_a_ZARVANY_nem_hozza_be_a_dev_extrakat_MERVE(self) -> None:
        """A javítás végponttól végpontig, **környezet-független** mintán.

        ⚠ Ez a teszt korábban a telepített `reportlab`-ot járta be. Az a
        fejlesztői gépen megvan, a CI-n nincs — a CI 2026-07-31-én emiatt bukott.
        Végigmérve: a motor teljes telepített láncán **nulla** extra-feltételű
        követelmény van, tehát a CI-n **egyáltalán nincs alkalmas valódi minta**;
        a mintát ezért magunkkal visszük (`tests/requirement_shapes.py`).
        """
        elvart = shapes.expected_closure()
        tiltott = shapes.extra_only_names()

        with shapes.installed_specimen():
            found, missing = guard.transitive_closure({shapes.ROOT})

        # 1) Az EREDETI hiba tunete: az extra-feltetelu nevek "nem mert"-kent
        #    jelennenek meg, mert egyikuk sincs telepitve (77 hamis bejegyzes).
        self.assertEqual(missing, set(), f"hamis 'nem mertem' bejegyzesek: {sorted(missing)}")

        # 2) A bejaras KOVETI a feltetel nelkuli elt -- enelkul egy "soha semmit
        #    nem kovetek" bejaras is atmenne, es a kapu uresen zold lenne.
        self.assertEqual(
            set(found),
            elvart,
            "a zarvany nem a feltetel nelkuli eleken elerheto halmaz",
        )

        # 3) Egyetlen extra mogotti nev sem kerult be -- nevesitve, hogy a
        #    bukas-uzenet megmondja, MELYIK szivargott at.
        beszivargott = sorted(tiltott & set(found))
        self.assertEqual(beszivargott, [], f"extra-feltetelu fuggoseg a zarvanyban: {beszivargott}")

    def test_a_kihagyas_MELYSEG_2_ben_is_all(self) -> None:
        """Az eredeti hiba a MÉLYEBB szinteken keletkezett, nem a gyökéren.

        A minta közbenső csomagja (`dcfixture-imaging`) csupa extra-feltételű
        követelményt hordoz — ha a bejárás csak a gyökéren szűrne, ezek itt
        bejönnének.
        """
        kozbenso = shapes.PACKAGES["dcfixture-imaging"]["requires"]
        self.assertTrue(kozbenso, "a melyseg-2 csomopont ures — a meres nem allit semmit")
        self.assertTrue(
            all("extra ==" in line for line in kozbenso),
            "a melyseg-2 csomopontnak CSUPA extra-feltetelu sora kell legyen",
        )

        with shapes.installed_specimen():
            found, _missing = guard.transitive_closure({shapes.ROOT})

        self.assertIn("dcfixture-imaging", found, "a melyseg-2 csomopont el sem erheto")
        for line in kozbenso:
            nev = line.split(";")[0].strip().split(" ")[0]
            with self.subTest(nev=nev):
                self.assertNotIn(nev, found, "melyseg-2 extra szivargott be")

    def test_a_MINTA_valoban_a_fixture_bol_jon_NEGATIV_kontroll(self) -> None:
        """A minta-nevek a `sys.path`-bejegyzés NÉLKÜL nem oldhatók fel.

        Enélkül nem tudnánk, hogy a fenti mérés a mintát járta-e be — vagy
        véletlenül valami mást, ami a gépen amúgy is ott van.
        """
        _found, missing = guard.transitive_closure({shapes.ROOT})
        self.assertEqual(
            missing,
            {shapes.ROOT},
            "a minta a fixture NELKUL is feloldhato — a meres nem a mintat merte",
        )

    def test_a_DURVA_elvaras_szabaly_ervenyes_ezen_az_adaton(self) -> None:
        """Az elvárás-oldal a `;` jelenlétéből dolgozik, a mért kód a markert
        **kiértékeli** — a kettőnek külön kell tévednie. Ez a teszt méri, hogy a
        durvább szabály ezen a rögzített adaton egybeesik a pontossal: minden
        feltételes sor `extra ==` feltételt hordoz.

        Egy tisztán környezeti marker (`; python_version >= "3.11"`) elrontaná az
        elvárást — ezért mérjük, hogy ilyen nincs a mintában.
        """
        feltetelesek = [
            line
            for package in shapes.PACKAGES.values()
            for line in package["requires"]
            if ";" in line
        ]
        self.assertTrue(feltetelesek, "nincs feltetelE sor — az elvaras nem allit semmit")
        for line in feltetelesek:
            with self.subTest(line=line):
                self.assertIn("extra ==", line, "tisztan kornyezeti marker a mintaban")


class ScopeTests(unittest.TestCase):
    """A kapu a SAJÁT láncot vizsgálja, nem az egész környezetet."""

    def test_a_globalis_kornyezet_idegen_csomagjai_NEM_szamitanak(self) -> None:
        """A gépen több száz idegen csomag van (köztük GPL-es). Ha a kapu mindet
        vizsgálná, a zaj miatt egy héten belül kikapcsolná valaki — és akkor
        rosszabbul állnánk, mint kapu nélkül."""
        declared = guard.declared_requirements(REPO)
        found, _missing = guard.transitive_closure(set(declared))
        osszes = sum(1 for _ in metadata.distributions())

        self.assertLess(
            len(found),
            osszes,
            "a kapu az EGESZ kornyezetet vizsgalja — az zaj lesz, nem meres",
        )
        self.assertGreater(len(found), 0, "a kapu semmit nem mert — vakon zold")

    def test_a_TRANZITIV_zar_bejarasa_tenyleg_megtortenik(self) -> None:
        """A deklarált `openpyxl` mögött ott van az `et-xmlfile` is. Ha a kapu
        csak a deklarált szintet nézné, egy GPL-es tranzitív függőség átmenne."""
        found, _missing = guard.transitive_closure({"openpyxl"})
        self.assertIn("openpyxl", found)
        self.assertIn("et-xmlfile", found, "a tranzitiv zar bejarasa NEM tortent meg")


if __name__ == "__main__":
    unittest.main()
