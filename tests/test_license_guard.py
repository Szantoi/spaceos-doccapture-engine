"""A licenc-kapu tesztjei — a G5 szabály MÉRVE, nem kimondva.

MIÉRT VAN EGYÁLTALÁN ILYEN TESZT
--------------------------------
A **G5** döntés MIT licencet ír elő, és a DC-01 felderítése kimérte, hogy ezt
**semmilyen gépi kapu nem őrizte**: a motor `tools/` mappájában nem volt
licenc-ellenőrző, tehát *„az első DC-01 függőséggel a szabály azonnal mérés
nélkülivé válik — GPL-függőséggel is lefordul és zöld a suite."*

A LEGÉRTÉKESEBB TESZT EBBEN A FÁJLBAN
-------------------------------------
`test_a_kapu_ELBUKTAT_egy_VALODI_GPL_csomagot`: nem kitalált licenc-szöveget
osztályoz, hanem egy **tényleg telepített** GPL-es csomagot deklarál egy eldobható
`pyproject.toml`-ban, és megméri, hogy a kapu elbukik rajta. Egy szöveg-osztályozó
teszt csak azt bizonyítja, hogy a *szabálylista* helyes; ez azt, hogy a **kapu
össze is áll**.

⚠ Ha az a csomag egyszer eltűnik a környezetből, ez a teszt **kimondottan kimarad**
(nem csendben zöldül) — a kihagyást a `measure_dependency_free.py` `KIHAGYVA`
számlálója is kiírja.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import license_guard as guard  # noqa: E402

CONFIG = REPO / "tools" / "licenses.json"


def _installed_gpl_package() -> tuple[str, str] | None:
    """Keres egy TÉNYLEG telepített, GPL-es csomagot — mérve, nem feltételezve."""
    config = guard.json.loads(CONFIG.read_text(encoding="utf-8"))
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if not name:
            continue
        text, _source = guard.license_of(dist)
        if guard.classify(text, config) == "tiltott":
            return guard.normalize(name), dist.version
    return None


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

    def _run(self, pyproject: str) -> subprocess.CompletedProcess:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        Path(tmp.name, "pyproject.toml").write_text(pyproject, encoding="utf-8")
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

    @unittest.skipUnless(
        _installed_gpl_package() is not None,
        "nincs telepitett GPL-es csomag ebben a kornyezetben — a meres KIMARAD",
    )
    def test_a_kapu_ELBUKTAT_egy_VALODI_GPL_csomagot(self) -> None:
        """Ez a fájl legértékesebb tesztje: nem kitalált szöveget osztályoz, hanem
        egy **tényleg telepített** GPL-es csomagot deklarál, és megméri, hogy a
        kapu elbukik rajta."""
        name, version = _installed_gpl_package()  # type: ignore[misc]
        proc = self._run(
            f'[project]\nname = "proba"\nversion = "0.0.0"\ndependencies = ["{name}"]\n'
        )
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("TILTOTT LICENC", proc.stdout)
        self.assertIn(name, proc.stdout)
        self.assertIn(version, proc.stdout)

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
        """A javítás végponttól végpontig: a zárvány csak futásidejű csomagokat tart."""
        found, missing = guard.transitive_closure({"reportlab"})

        self.assertEqual(missing, set(), f"hamis 'nem mertem' bejegyzesek: {sorted(missing)}")
        for dev in ("flit", "sphinx", "pytest", "coverage", "check-manifest", "certifi"):
            with self.subTest(dev=dev):
                self.assertNotIn(dev, found, f"{dev} NEM szallitott fuggoseg")
        self.assertIn("pillow", found, "a valodi futasideju fuggoseg kimaradt")
        self.assertLess(len(found), 15, f"a zarvany tul nagy ({len(found)}) — a zaj visszatert")


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
