"""A teljes irat-elemzési lánc — unit ÉS integráció (QUALITY §4).

`ExtractionTests` a címke→érték kinyerést méri egységként; az
`EndToEndTests` a **valódi láncot**: fájl → sorok → felismerés → mezők →
önellenőrző számtan → rekord, a repóban szállított **valódi profilokkal**.

Az integrációs rész azért kell, mert az egységek külön-külön zöldek lehetnek
úgy, hogy a lánc mégsem áll össze — és ez a fajta hiba csak a végpontok között
látszik.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from doccapture.core.config import CaptureConfig
from doccapture.core.documents import DocumentProfile, FieldSpec, extract_fields
from doccapture.core.errors import ConfigurationError
from doccapture.core.models import Confidence, InputKind, SourceEvidence
from doccapture.core.tabular import ColumnType, TabularOptions
from doccapture.infrastructure.profile_registry import (
    load_profiles,
    select_profiles,
)
from doccapture.infrastructure.text_lines import TextLineReader
from doccapture.usecases.analyze_document import PROFILE_FIELD, DocumentAnalyzer

REPO = Path(__file__).resolve().parent.parent
EVIDENCE = SourceEvidence("irat.txt", "sha256:abc")

PROFIL = DocumentProfile(
    profile_id="proba",
    required_anchors=("munkalap",),
    fields=(
        FieldSpec("szam", ("Munkaszám", "Job number"), ColumnType.TEXT, required=True),
        FieldSpec("db", ("Darabszám",), ColumnType.INTEGER),
        FieldSpec("megjegyzes", ("Megjegyzés",), ColumnType.TEXT, field_type="keziras"),
    ),
)


class ExtractionTests(unittest.TestCase):
    def test_EGY_soros_cimke_ertek(self) -> None:
        fields, _ = extract_fields(["Munkalap", "Munkaszám: A-123"], PROFIL, evidence=EVIDENCE)

        self.assertEqual(fields["szam"].value, "A-123")
        self.assertIs(fields["szam"].confidence, Confidence.CONFIRMED)
        self.assertEqual(fields["szam"].evidence.locator, "L2")

    def test_KET_soros_elrendezes(self) -> None:
        """Szkennelésnél a címke és az értéke gyakran külön sorba kerül."""
        fields, _ = extract_fields(
            ["Munkalap", "Munkaszám:", "", "A-123"], PROFIL, evidence=EVIDENCE
        )
        self.assertEqual(fields["szam"].value, "A-123")
        self.assertEqual(fields["szam"].evidence.locator, "L4")

    def test_tobb_cimke_valtozat_ugyanarra_a_mezore(self) -> None:
        fields, _ = extract_fields(["Munkalap", "Job number: B-7"], PROFIL, evidence=EVIDENCE)
        self.assertEqual(fields["szam"].value, "B-7")

    def test_a_valasztojelek_levalnak(self) -> None:
        for sor in ("Munkaszám: A-1", "Munkaszám - A-1", "Munkaszám = A-1", "Munkaszám . A-1"):
            with self.subTest(sor=sor):
                fields, _ = extract_fields(["Munkalap", sor], PROFIL, evidence=EVIDENCE)
                self.assertEqual(fields["szam"].value, "A-1")

    def test_a_nem_talalt_mezo_HIANY_nem_kivetel(self) -> None:
        fields, notes = extract_fields(["Munkalap"], PROFIL, evidence=EVIDENCE)

        self.assertIs(fields["szam"].confidence, Confidence.MISSING)
        self.assertIn("nem találtam címkét", fields["szam"].note)
        # A KOTELEZO mezo hianyat kimondjuk, kulonben a hianyos irat teljesnek latszik.
        self.assertTrue(any("kötelező mező nem található" in n for n in notes), notes)

    def test_a_KETERTELMU_cimke_JELOLVE_lesz(self) -> None:
        """Két eltérő érték ugyanarra a címkére: valamelyik biztosan rossz.
        Az elsőt csendben elfogadni működne — és épp ezért lenne veszélyes."""
        fields, notes = extract_fields(
            ["Munkalap", "Munkaszám: A-1", "Munkaszám: B-2"], PROFIL, evidence=EVIDENCE
        )

        self.assertIs(fields["szam"].confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("ELTÉRŐ értékkel", fields["szam"].note)
        self.assertIn("L2", fields["szam"].note)
        self.assertIn("L3", fields["szam"].note)
        self.assertTrue(any("kétértelmű mező" in n for n in notes), notes)

    def test_az_UGYANAZ_ertek_tobb_helyen_NEM_ketertelmu(self) -> None:
        """A másik irány: egy fejléc-lábléc ismétlés nem hiba."""
        fields, _ = extract_fields(
            ["Munkalap", "Munkaszám: A-1", "Munkaszám: A-1"], PROFIL, evidence=EVIDENCE
        )
        self.assertIs(fields["szam"].confidence, Confidence.CONFIRMED)

    def test_az_M7_jelolt_mezot_NEM_olvassuk(self) -> None:
        fields, _ = extract_fields(
            ["Munkalap", "Megjegyzés: kézzel írt szöveg"],
            PROFIL,
            evidence=EVIDENCE,
            human_only_field_types=["keziras"],
        )
        self.assertIsNone(fields["megjegyzes"].value)
        self.assertIn("emberi kitöltésre", fields["megjegyzes"].note)

    def test_az_ertelmezes_UGYANAZ_mint_a_tablazatos_uton(self) -> None:
        """Egy igazság: a kétértelmű szám itt is hiány, nem tipp."""
        fields, _ = extract_fields(
            ["Munkalap", "Darabszám: 1,234"], PROFIL, evidence=EVIDENCE
        )
        self.assertIsNone(fields["db"].value)
        self.assertIn("kétértelmű", fields["db"].note)

        fields, _ = extract_fields(
            ["Munkalap", "Darabszám: 1,234"],
            PROFIL,
            options=TabularOptions(decimal_separator="."),
            evidence=EVIDENCE,
        )
        self.assertEqual(fields["db"].value, 1234)


class LabelCollisionTests(unittest.TestCase):
    """⚠ REGRESSZIÓ: a rövidebb címke elszívta a hosszabb mező sorát.

    A hibát a saját végponttól végpontig futó tesztem hozta elő, és **kétszeresen
    tanulságos**:

    1. az `"Ado"` címke puszta részszövegként beleillett az `"Adoalap: 100000"`
       sorba, tehát az adó mezőbe `"alap: 100000"` került → hiány lett belőle;
    2. **a hibát elmaszkolta a származtatás** (M4 kitöltötte az adót a
       végösszegből, a *helyes* értékkel). A kimenet **jónak látszott**, miközben
       a kinyerés rossz volt — a javító mechanizmus elrejtette a hibát, amit
       javítani hivatott.

    Ezért itt a mérés a **kinyerésre** irányul, származtatás nélküli profilon.
    """

    COLLIDING = DocumentProfile(
        profile_id="utkozo",
        required_anchors=("bizonylat",),
        fields=(
            FieldSpec("adoalap", ("Adoalap",), ColumnType.NUMBER),
            FieldSpec("ado", ("Ado",), ColumnType.NUMBER),
        ),
    )

    def test_a_ROVIDEBB_cimke_nem_viszi_el_a_hosszabb_soraat(self) -> None:
        fields, _ = extract_fields(
            ["Bizonylat", "Adoalap: 100000", "Ado: 27000"],
            self.COLLIDING,
            evidence=EVIDENCE,
        )

        self.assertEqual(fields["adoalap"].value, 100000.0)
        self.assertEqual(fields["ado"].value, 27000.0, "a rovid cimke elvitte a hosszabb sorat")
        self.assertIs(fields["ado"].confidence, Confidence.CONFIRMED)
        self.assertEqual(fields["ado"].evidence.locator, "L3")

    def test_a_cimke_szo_KOZEPEN_nem_illeszkedik(self) -> None:
        """Szóhatár nélkül a `"Ado"` a `"Kiadoi"` szóba is beleillene."""
        from doccapture.core.documents.extract import label_matches

        self.assertEqual(label_matches("ado: 27000", "ado"), 0)
        self.assertEqual(label_matches("adoalap: 100000", "ado"), -1)
        self.assertEqual(label_matches("kiadoi koltseg: 5", "ado"), -1)
        self.assertEqual(label_matches("netto ado osszege: 5", "ado"), 6)

    def test_a_TELJES_szoval_hosszabb_cimke_nyeri_a_sort(self) -> None:
        """A szóhatár itt NEM elég: mindkét címke szóhatáron áll. A leghosszabb
        illeszkedő címke nyeri a sort — különben az `"Ido"` elvinné az
        `"Osszes ido"` sorát, csendben."""
        profil = DocumentProfile(
            profile_id="ido-utkozo",
            required_anchors=("munkalap",),
            fields=(
                FieldSpec("ido", ("Ido",), ColumnType.NUMBER),
                FieldSpec("osszes", ("Osszes ido",), ColumnType.NUMBER),
            ),
        )
        fields, _ = extract_fields(
            ["Munkalap", "Ido: 5", "Osszes ido: 30"], profil, evidence=EVIDENCE
        )

        self.assertEqual(fields["ido"].value, 5.0)
        self.assertEqual(fields["osszes"].value, 30.0)
        self.assertEqual(fields["ido"].evidence.locator, "L2")
        self.assertEqual(fields["osszes"].evidence.locator, "L3")

    def test_a_kinyeres_UTKOZES_NELKUL_is_helyes_a_szallitott_profilon(self) -> None:
        """A valódi bizonylat-profilon: az adó mező LEOLVASVA legyen, ne
        származtatva — különben a maszkolás visszatért."""
        profiles = load_profiles(REPO / "profiles")
        bizonylat = next(p for p in profiles if p.profile_id == "ketoldalu-kereskedelmi-irat")
        fields, _ = extract_fields(
            ["BIZONYLAT", "Adoalap: 100000", "Ado: 27000", "Vegosszeg: 127000"],
            bizonylat,
            evidence=EVIDENCE,
        )

        self.assertEqual(fields["tax_amount"].value, 27000.0)
        self.assertIs(
            fields["tax_amount"].confidence,
            Confidence.CONFIRMED,
            "az ado nem LEOLVASVA jott -- a cimke-utkozes visszatert",
        )


class AnalyzerTests(unittest.TestCase):
    def test_a_fel_nem_ismert_irat_eseten_MEGALLUNK(self) -> None:
        """Egy rossz profillal kinyert mező rosszabb, mint a semmi: helyesnek
        látszik, és senki nem nézi meg."""
        analyzer = DocumentAnalyzer([PROFIL])
        record = analyzer.analyze(
            ["Teljesen más szöveg"], input_kind=InputKind.TEXT_LAYER_DOCUMENT, evidence=EVIDENCE
        )

        self.assertIs(record.fields[PROFILE_FIELD].confidence, Confidence.MISSING)
        # CSAK a profil-mezo van benne -- mezoket nem nyertunk ki.
        self.assertEqual(list(record.fields), [PROFILE_FIELD])
        self.assertTrue(
            any("nem eldönthető" in n for n in record.diagnostics), record.diagnostics
        )

    def test_a_rekord_a_felismert_tipust_MEZOKENT_hordozza(self) -> None:
        analyzer = DocumentAnalyzer([PROFIL])
        record = analyzer.analyze(
            ["Munkalap", "Munkaszám: A-1"],
            input_kind=InputKind.TEXT_LAYER_DOCUMENT,
            evidence=EVIDENCE,
        )
        self.assertEqual(record.fields[PROFILE_FIELD].value, "proba")
        self.assertIs(record.fields[PROFILE_FIELD].confidence, Confidence.CONFIRMED)

    def test_a_rekord_NEM_tartalmaz_parositast_vagy_atvaltast(self) -> None:
        """A G1/G2 határ: a motor megmondja, mi van a papíron. Azt nem, hogy mi
        kerüljön a fogadó rendszerbe."""
        analyzer = DocumentAnalyzer([PROFIL])
        record = analyzer.analyze(
            ["Munkalap", "Munkaszám: A-1", "Darabszám: 5"],
            input_kind=InputKind.TEXT_LAYER_DOCUMENT,
            evidence=EVIDENCE,
        )
        self.assertEqual(
            sorted(record.fields), sorted([PROFILE_FIELD, "szam", "db", "megjegyzes"])
        )


class EndToEndTests(unittest.TestCase):
    """Fájl → sorok → felismerés → mezők → számtan → rekord, VALÓDI profilokkal."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.profiles = load_profiles(REPO / "profiles")

    def _run(self, content: str, name: str = "irat.txt"):
        (self.root / name).write_text(content, encoding="utf-8")
        config = CaptureConfig(input_root=str(self.root))
        lines, evidence = TextLineReader(config).read(name)
        analyzer = DocumentAnalyzer(self.profiles, config)
        return analyzer.analyze(
            lines, input_kind=InputKind.TEXT_LAYER_DOCUMENT, evidence=evidence
        )

    def test_a_szallitott_profilok_betoltodnek(self) -> None:
        ids = sorted(p.profile_id for p in self.profiles)
        self.assertEqual(ids, ["ketoldalu-kereskedelmi-irat", "munkalap"])

    def test_MUNKALAP_teljes_lanc_a_szamtannal(self) -> None:
        record = self._run(
            "MUNKALAP\n"
            "Munkaszam: MK-2026-001\n"
            "Muvelet: elokeszites\n"
            "Gep: G-04\n"
            "Darabszam: 20\n"
            "Ciklusido: 1,5\n"
            "Osszes ido: 30\n"
        )

        self.assertEqual(record.fields[PROFILE_FIELD].value, "munkalap")
        self.assertEqual(record.fields["job_number"].value, "MK-2026-001")
        self.assertEqual(record.fields["quantity"].value, 20)
        self.assertEqual(record.fields["total_time"].value, 30.0)
        # Az onellenorzes ALL: 1,5 x 20 = 30
        self.assertTrue(
            any("[ok] osszes ido" in n for n in record.diagnostics), record.diagnostics
        )
        self.assertIs(record.input_kind, InputKind.TEXT_LAYER_DOCUMENT)

    def test_MUNKALAP_bomlo_onellenorzessel(self) -> None:
        """A számtan itt fog egy valódi hibát: 1,5 × 20 ≠ 40."""
        record = self._run(
            "MUNKALAP\nMunkaszam: MK-1\nDarabszam: 20\nCiklusido: 1,5\nOsszes ido: 40\n"
        )

        self.assertTrue(
            any("⚠ önellenőrzés BOMLIK" in n for n in record.diagnostics), record.diagnostics
        )
        self.assertEqual(record.fields["total_time"].value, 40.0, "nem javitottuk")
        self.assertIs(record.fields["total_time"].confidence, Confidence.NEEDS_REVIEW)
        self.assertTrue(record.needs_human)

    def test_MUNKALAP_hianyzo_darabszam_VISSZASZAMOLVA(self) -> None:
        """M4 élesben: a darabszám kézírásos, de az idők gépiek."""
        record = self._run(
            "MUNKALAP\nMunkaszam: MK-1\nCiklusido: 2\nOsszes ido: 30\n"
        )

        self.assertEqual(record.fields["quantity"].value, 15.0)
        self.assertIs(record.fields["quantity"].confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("M4", record.fields["quantity"].note)

    def test_BIZONYLAT_teljes_lanc(self) -> None:
        record = self._run(
            "BIZONYLAT\n"
            "Bizonylatszam: B-2026-77\n"
            "Kelt: 2026-07-30\n"
            "Adoalap: 100000\n"
            "Ado: 27000\n"
            "Vegosszeg: 127000\n"
        )

        self.assertEqual(record.fields[PROFILE_FIELD].value, "ketoldalu-kereskedelmi-irat")
        self.assertEqual(record.fields["document_number"].value, "B-2026-77")
        self.assertEqual(record.fields["net_amount"].value, 100000.0)
        self.assertTrue(
            any("[ok] vegosszeg" in n for n in record.diagnostics), record.diagnostics
        )

    def test_a_KET_PROFIL_kulon_utra_megy_UGYANAZON_a_bemeneti_uton(self) -> None:
        """Ez a szelet központi állítása: a profil és az `InputKind` KÉT
        FÜGGETLEN tengely. Ugyanaz a szöveg-út, két különböző irat-elemzés."""
        munkalap = self._run("MUNKALAP\nMunkaszam: M-1\n", "a.txt")
        bizonylat = self._run("BIZONYLAT\nBizonylatszam: B-1\n", "b.txt")

        self.assertIs(munkalap.input_kind, bizonylat.input_kind)
        self.assertNotEqual(
            munkalap.fields[PROFILE_FIELD].value, bizonylat.fields[PROFILE_FIELD].value
        )
        self.assertIn("job_number", munkalap.fields)
        self.assertIn("document_number", bizonylat.fields)
        self.assertNotIn("job_number", bizonylat.fields)

    def test_a_bizonyitek_a_SORRA_mutat(self) -> None:
        record = self._run("MUNKALAP\nMunkaszam: MK-1\n")
        evidence = record.fields["job_number"].evidence

        self.assertEqual(evidence.relative_path, "irat.txt")
        self.assertTrue(evidence.content_hash.startswith("sha256:"))
        self.assertEqual(evidence.locator, "L2")

    def test_a_forras_MAPPA_valtozatlan_marad(self) -> None:
        """M10 mérve, nem állítva."""
        from doccapture.infrastructure.evidence import content_hash

        (self.root / "irat.txt").write_text("MUNKALAP\nMunkaszam: M-1\n", encoding="utf-8")

        def snapshot():
            return {
                p.name: (p.stat().st_size, p.stat().st_mtime_ns, content_hash(p))
                for p in sorted(self.root.rglob("*")) if p.is_file()
            }

        before = snapshot()
        config = CaptureConfig(input_root=str(self.root))
        lines, evidence = TextLineReader(config).read("irat.txt")
        DocumentAnalyzer(self.profiles, config).analyze(
            lines, input_kind=InputKind.TEXT_LAYER_DOCUMENT, evidence=evidence
        )
        self.assertEqual(before, snapshot())


class RegistryTests(unittest.TestCase):
    def test_a_hibas_profil_INDULASKOR_bukik_es_MEGNEVEZI_a_fajlt(self) -> None:
        """Egy tíz profilos katalógusban a „hiányzó labels" üzenet önmagában
        használhatatlan — nem tudod, melyik fájlt nyisd meg."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "rossz.json").write_text(
                '{"profile_id": "x", "required_anchors": ["a"], '
                '"fields": [{"key": "k", "labels": "nem lista"}]}',
                encoding="utf-8",
            )
            with self.assertRaises(ConfigurationError) as ctx:
                load_profiles(tmp)
        self.assertIn("rossz.json", str(ctx.exception))
        self.assertIn("listát vár", str(ctx.exception))

    def test_az_azonosito_utkozes_HIBA_nem_felulirás(self) -> None:
        """A néma felülírás azt jelentené, hogy a katalógus tartalma a fájlok
        olvasási sorrendjétől függ — és a sorrend fájlrendszerenként más."""
        with tempfile.TemporaryDirectory() as tmp:
            for nev in ("a.json", "b.json"):
                Path(tmp, nev).write_text(
                    '{"profile_id": "ugyanaz", "required_anchors": ["x"]}', encoding="utf-8"
                )
            with self.assertRaises(ConfigurationError) as ctx:
                load_profiles(tmp)
        self.assertIn("ugyanazzal az azonosítóval", str(ctx.exception))

    def test_a_nem_letezo_konyvtar_kimondott_hiba(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_profiles(Path(tempfile.gettempdir()) / "nincs-ilyen-konyvtar-remelem")

    def test_a_szukites_mukodik(self) -> None:
        profiles = load_profiles(REPO / "profiles")
        csak_egy = select_profiles(profiles, ["munkalap"])
        self.assertEqual([p.profile_id for p in csak_egy], ["munkalap"])
        self.assertEqual(len(select_profiles(profiles, None)), len(profiles))

    def test_az_ELGEPELT_profil_nev_hiba(self) -> None:
        """Csendben azt jelentené, hogy egy irat-típust soha nem ismerünk fel."""
        profiles = load_profiles(REPO / "profiles")
        with self.assertRaises(ConfigurationError) as ctx:
            select_profiles(profiles, ["munkalp"])
        self.assertIn("Ismeretlen profil-azonosító", str(ctx.exception))

    def test_a_szallitott_profilok_koroda(self) -> None:
        """A profil ADAT: amit kiírunk, azt vissza is kell tudnunk olvasni."""
        for profile in load_profiles(REPO / "profiles"):
            with self.subTest(profile=profile.profile_id):
                self.assertEqual(DocumentProfile.from_dict(profile.to_dict()), profile)


if __name__ == "__main__":
    unittest.main()
