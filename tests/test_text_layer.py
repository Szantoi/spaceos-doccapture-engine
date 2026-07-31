"""A szövegréteges út kapui: mérés, konverzió, geometria, napló, bizonyíték.

A FIXTURE KÉZZEL ÍRT PDF-BÁJTOKBÓL ÁLL — ÉS EZ MÉRT DÖNTÉS
-----------------------------------------------------------
A `document` extra egyetlen csomagja az **olvasó**; PDF-et **írni** nem tud. Egy
író-könyvtár (reportlab) csak a fixture kedvéért nem kerül be: az a kereshető
PDF írásának szelete (DC-01b), és egy teszt-függőség ugyanúgy függőség.

⚠ A terv ezt „NEM MÉRT" tételként vitte fel (minden korábbi mérés reportlabbal
készült). **Megmérve, 2026-07-31:** a lenti 721 bájtos, kézzel írt PDF-et a
telepített olvasó (4.30.0 / libpdfium 6462) hibátlanul megnyitja, 3 téglalapot
és 64 karaktert ad rajta. A fixture tehát **járható**, tartalék-terv (commitolt
bináris + dev-only generátor) nem kell — és üzleti bináris sem kerül a repóba (M13).
"""

from __future__ import annotations

import logging
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from doccapture.core.config import CaptureConfig  # noqa: E402
from doccapture.core.errors import SourceUnreadableError  # noqa: E402
from doccapture.core.layout import TextFragment  # noqa: E402
from doccapture.core.text_layer_options import TextLayerOptions  # noqa: E402
from doccapture.infrastructure.textlayer.probe import (  # noqa: E402
    TextLayerVerdict,
    measure_text_layer,
)
from doccapture.infrastructure.textlayer.reader import PdfiumTextLayerReader  # noqa: E402
from doccapture.usecases.read_document_text import DocumentTextReader  # noqa: E402

PAGE_WIDTH = 595.276
PAGE_HEIGHT = 841.89


def build_pdf(pages, page_w=PAGE_WIDTH, page_h=PAGE_HEIGHT) -> bytes:
    """Minimális, több lapos PDF kézzel.

    `pages`: laponként `(x, y_alulrol, betumeret, szoveg)` négyesek listája.
    A koordináta SZÁNDÉKOSAN alulról értendő — ez a PDF saját konvenciója, és a
    teszt pont azt méri, hogy az adapter ezt bal-felsőre fordítja.
    """
    objects: list[bytes] = []
    page_object_ids: list[int] = []

    # 1: katalogus, 2: lapfa, majd laponkent (lap-objektum + tartalom), vegul font.
    next_id = 3
    page_entries: list[tuple[int, int, bytes]] = []
    for lines in pages:
        parts = []
        for x, y, size, text in lines:
            escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            parts.append(f"BT /F1 {size} Tf {x} {y} Td ({escaped}) Tj ET")
        content = "\n".join(parts).encode("latin-1")
        page_id, content_id = next_id, next_id + 1
        next_id += 2
        page_object_ids.append(page_id)
        page_entries.append((page_id, content_id, content))
    font_id = next_id

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{pid} 0 R" for pid in page_object_ids)
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>".encode("latin-1")
    )
    for page_id, content_id, content in page_entries:
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w} {page_h}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("latin-1")
        )
        objects.append(
            b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n"
    ).encode()
    out += b"%%EOF\n"
    return bytes(out)


# --- fixture-tartalmak, kimondott karakterszamokkal -----------------------

# ~52 erdemi karakter: BOVEN a 32-es kuszob folott -> USABLE.
TARTALOM_LAP = [
    (72.0, 700.0, 12, "Bal hasab elso sora"),
    (320.0, 700.0, 12, "Jobb hasab elso sora"),
    (72.0, 660.0, 12, "Bal hasab masodik sora"),
]

# A MERT CSAPDA: egy szkennelt lap, amin CSAK a szkenner belyegzoje van.
# Erdemi karakter: 25 -- a 32-es kuszob ALATT, de nem nulla. Egy
# `count_chars > 0` boolean ezt dokumentum-tartalomnak minositene.
BELYEGZO_LAP = [(72.0, 40.0, 8, "Szkennelve 2026-07-31 12:00")]

# Egyetlen, a lapszelesseg nagy reszet atfogo futam: OSSZEOLVADT hasabok (M2).
OSSZEOLVADT_LAP = [
    (
        40.0,
        700.0,
        12,
        "Bal hasab szovege itt folytatodik es a jobb hasab szovege ide olvadt",
    )
]


class _PdfFixture:
    """Ideiglenes könyvtár egy PDF-fel — a bemeneti gyökér is ez lesz."""

    def __init__(self, pages, name: str = "irat.pdf") -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.name = name
        (self.root / name).write_bytes(build_pdf(pages))

    def config(self, **text_layer_kwargs) -> CaptureConfig:
        config = CaptureConfig(input_root=str(self.root))
        if text_layer_kwargs:
            config.text_layer = TextLayerOptions(**text_layer_kwargs)
        return config

    def close(self) -> None:
        self._tmp.cleanup()


# ==========================================================================
# K3 — a szövegréteg-verdikt fail-closed
# ==========================================================================


class TextLayerVerdictTests(unittest.TestCase):
    """A háromállapotú verdikt, MINDKÉT irányból mérve."""

    def test_a_valodi_tartalom_HASZNALHATO(self) -> None:
        """A másik irány kontrollja: egy kapu, ami mindent elutasít, haszontalan."""
        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            measurement = measure_text_layer(
                fixture.root / fixture.name, TextLayerOptions()
            )
            self.assertIs(measurement.verdict, TextLayerVerdict.USABLE)
            self.assertTrue(measurement.usable)
            self.assertGreaterEqual(measurement.total_chars, 32)
        finally:
            fixture.close()

    def test_a_szkenner_belyegzo_NEM_dokumentum_tartalom(self) -> None:
        """A mért csapda: 25 érdemi karakter 1 téglalapban → KÉTÉRTELMŰ.

        Egy `count_chars > 0` boolean ezt USABLE-nek venné, a lap a szövegréteges
        úton menne tovább, és a valódi tartalma (a kép) **csendben elveszne**.
        """
        fixture = _PdfFixture([BELYEGZO_LAP])
        try:
            measurement = measure_text_layer(
                fixture.root / fixture.name, TextLayerOptions()
            )
            self.assertIs(measurement.verdict, TextLayerVerdict.AMBIGUOUS)
            self.assertFalse(
                measurement.usable,
                "a ketertelmu verdikt NEM csuszhat at igenbe (fail-closed)",
            )
            self.assertGreater(measurement.total_chars, 0, "van szoveg, csak keves")
            self.assertLess(measurement.total_chars, 32)
        finally:
            fixture.close()

    def test_a_kapu_a_KUSZOBRE_lat_nem_csak_a_trivialis_nullara(self) -> None:
        """Negatív kontroll: küszöb=1-gyel ugyanaz a bélyegző-lap USABLE lesz.

        Enélkül nem tudnánk, hogy a fenti teszt azért zöld, mert a küszöb
        működik — vagy azért, mert a mérés csak a 0 karakteres esetet fogja.
        """
        fixture = _PdfFixture([BELYEGZO_LAP])
        try:
            measurement = measure_text_layer(
                fixture.root / fixture.name,
                TextLayerOptions(min_usable_chars_per_page=1),
            )
            self.assertIs(measurement.verdict, TextLayerVerdict.USABLE)
        finally:
            fixture.close()

    def test_a_verdikt_INDOKOT_hordoz(self) -> None:
        """Egy verdikt, ami nem mondja meg, mit mért mihez képest, nem ellenőrizhető."""
        fixture = _PdfFixture([BELYEGZO_LAP])
        try:
            measurement = measure_text_layer(
                fixture.root / fixture.name, TextLayerOptions()
            )
            self.assertIn("32", measurement.reason, "a KUSZOB szerepeljen az indokban")
            self.assertRegex(measurement.reason, r"\d+ karakter")
        finally:
            fixture.close()

    def test_a_hasznalhatatlan_szovegreteg_KIMONDOTT_hibat_ad(self) -> None:
        """A use-case fail-closed: NEM esik át csendben a felismerő útra."""
        fixture = _PdfFixture([BELYEGZO_LAP])
        try:
            with self.assertRaises(SourceUnreadableError) as ctx:
                DocumentTextReader(fixture.config()).read(fixture.name)
            uzenet = str(ctx.exception)
            self.assertIn("ambiguous", uzenet)
            self.assertIn("min_usable_chars_per_page", uzenet, "a hivo tudja meg, mit allithat")
        finally:
            fixture.close()

    def test_a_VEGYES_dokumentumot_kimondjuk(self) -> None:
        """Részben szkennelt iratnál a küszöb alatti lapok NEM tűnhetnek üresnek."""
        fixture = _PdfFixture([TARTALOM_LAP, BELYEGZO_LAP])
        try:
            measurement = measure_text_layer(
                fixture.root / fixture.name, TextLayerOptions()
            )
            self.assertIs(measurement.verdict, TextLayerVerdict.USABLE)
            self.assertIn("VEGYES", measurement.reason)
            self.assertEqual(measurement.page_count, 2)
        finally:
            fixture.close()


# ==========================================================================
# K4 — geometria-invariáns ÉS a tényleges koordináta
# ==========================================================================


class GeometryTests(unittest.TestCase):
    """A konverzió helyessége — és amit az invariáns egymagában NEM fog meg."""

    def test_az_alul_nullas_koordinata_bal_felsore_fordul(self) -> None:
        """A TÉNYLEGES pozíciót mérjük, nem csak a reláció fennállását.

        A szöveg alulról y=700-ra van írva, a lap 841.89 pont magas. A helyes
        `y_top` tehát ~133.3 (= 841.89 − a téglalap felső éle), NEM ~699.9.

        ⚠ Ez a különbségtétel a lényeg: egy **index szerinti** naiv átvétel
        (`y_top = rect[1]`) az invariánst KIELÉGÍTENÉ (699.87 < 708.59), tehát
        a `__post_init__` átengedné — pedig a lap fejjel lefelé állna. Csak ez
        a mérés fogja meg.
        """
        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            pages = PdfiumTextLayerReader(fixture.config()).read_pages(fixture.name)
            fragment = pages[0].fragments[0]

            self.assertAlmostEqual(fragment.y_top, 133.3, delta=1.5)
            self.assertAlmostEqual(fragment.y_bottom, 142.0, delta=1.5)
            self.assertLess(
                fragment.y_top,
                PAGE_HEIGHT / 2,
                "a lap TETEJEN levo szoveg y_top-ja a lap felso feleben van",
            )
        finally:
            fixture.close()

    def test_a_nev_szerinti_naiv_atvetel_ELBUKIK(self) -> None:
        """Mutáció: a natív „felső" élt `y_top`-ra véve az invariáns megfog.

        Ez a két elrontási mód közül az EGYIK — a másikat (index szerinti
        átvétel) a fenti pozíció-mérés fogja meg. A kettő együtt fedi le a
        konverziót; külön-külön egyik sem elég.
        """
        with self.assertRaises(ValueError) as ctx:
            TextFragment(
                text="proba",
                raw_confidence=1.0,
                x_left=72.876,
                y_top=708.592,  # a NATIV felso el -- alul-nullas rendszerben nagyobb
                x_right=176.880,
                y_bottom=699.868,
            )
        self.assertIn("alul-nullás", str(ctx.exception))

    def test_a_fordított_vagy_nulla_szelessegu_teglalap_ELBUKIK(self) -> None:
        with self.assertRaises(ValueError):
            TextFragment(
                text="proba", raw_confidence=1.0,
                x_left=100.0, y_top=10.0, x_right=100.0, y_bottom=20.0,
            )

    def test_a_lapmeret_TORT_pont_ertek(self) -> None:
        """Az int→float váltás mért oka: az A4 pontban nem egész."""
        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            page = PdfiumTextLayerReader(fixture.config()).read_pages(fixture.name)[0]
            self.assertAlmostEqual(page.width, PAGE_WIDTH, delta=0.01)
            self.assertAlmostEqual(page.height, PAGE_HEIGHT, delta=0.01)
            self.assertNotEqual(
                page.width, int(page.width), "int-ben ez az ertek csendben torzulna"
            )
        finally:
            fixture.close()

    def test_a_lapmeret_turessel_illeszkedik_a_deklaralt_fizikai_merethez(self) -> None:
        """A pixelben átadott lapméret (~4,17-szeres) NEM fér a tűrésbe."""
        options = TextLayerOptions()
        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            page = PdfiumTextLayerReader(fixture.config()).read_pages(fixture.name)[0]
            self.assertLessEqual(
                abs(page.width - PAGE_WIDTH), options.page_size_tolerance_pt
            )
            # negativ kontroll: 300 DPI-s pixel-ertek ugyanerre a lapra
            pixel_width = PAGE_WIDTH * 300 / 72
            self.assertGreater(
                abs(pixel_width - PAGE_WIDTH),
                options.page_size_tolerance_pt,
                "a tures atengedne a pixel-erteket — akkor nem merne semmit",
            )
        finally:
            fixture.close()


# ==========================================================================
# K5 — az `x_right` kitöltöttsége ARÁNYKÉNT, a könyvtár ellen ellenőrizve
# ==========================================================================


class RightEdgeTests(unittest.TestCase):
    def test_az_x_right_MINDEN_fragmensen_a_konyvtar_jobb_szele(self) -> None:
        """Nem boolean, hanem ARÁNY — és nem „nem None", hanem EGYENLŐSÉG.

        ⚠ A „hiányzó `x_right` bukik a konstruktoron" kontroll **tautológia**
        lenne (a Python argumentum-kötését mérné). A valódi kockázat a
        **fabrikált** érték: egy `x_left + 1` az invariánson átmegy. Ezért a
        mérés a könyvtár saját `get_rect` jobb szélével veti össze.
        """
        import pypdfium2 as pdfium

        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            pages = PdfiumTextLayerReader(fixture.config()).read_pages(fixture.name)
            fragments = pages[0].fragments

            document = pdfium.PdfDocument(str(fixture.root / fixture.name))
            try:
                text_page = document[0].get_textpage()
                vart = [text_page.get_rect(i)[2] for i in range(text_page.count_rects())]
                text_page.close()
            finally:
                document.close()

            self.assertEqual(len(fragments), len(vart), "fragmens-darabszam elteres")
            egyezik = sum(
                1
                for fragment, expected in zip(fragments, vart)
                if abs(fragment.x_right - expected) < 0.001
            )
            self.assertEqual(
                egyezik,
                len(fragments),
                f"x_right egyezes: {egyezik}/{len(fragments)} — a hianyzo vagy "
                f"fabrikalt jobb szel utolag potolhatatlan",
            )
            # A merés SZAMKENT is kiirva: egy `assertTrue` nem mondana meg, hany darabon all.
            self.assertGreater(len(fragments), 1, "egyetlen fragmensen az arany nem allitas")
        finally:
            fixture.close()


# ==========================================================================
# K7 — napló-higiénia
# ==========================================================================


class LoggingHygieneTests(unittest.TestCase):
    def test_a_naplo_NEM_visz_ki_tartalmat_es_abszolut_utat(self) -> None:
        """Darabszám és szerkezet igen; fragmens-tartalom és abszolút út SOHA."""
        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            with self.assertLogs("doccapture", level=logging.INFO) as captured:
                DocumentTextReader(fixture.config()).read(fixture.name)

            teljes = "\n".join(captured.output)
            self.assertIn("document_text.read", teljes, "a lepes egyaltalan naplozodjon")
            self.assertNotIn(
                "Bal hasab elso sora",
                teljes,
                "fragmens-TARTALOM kerult a naploba — uzleti adat egy lazabban vedett fajlban",
            )
            self.assertNotIn(
                str(fixture.root),
                teljes,
                "ABSZOLUT ut kerult a naploba — felfedi a gepi konyvtarszerkezetet",
            )
            self.assertIn("pages=", teljes, "a darabszam viszont KELL a hibakereseshez")
        finally:
            fixture.close()


# ==========================================================================
# K12 — bizonyíték-lánc (M13)
# ==========================================================================


class EvidenceChainTests(unittest.TestCase):
    def test_a_bizonyitek_sha256_eloTAGGAL_jon(self) -> None:
        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            result = DocumentTextReader(fixture.config()).read(fixture.name)
            self.assertTrue(
                result.evidence.content_hash.startswith("sha256:"),
                "eloTAG nelkul egy kesobbi hash-valtas megvaltozott forrasnak latszana",
            )
            self.assertEqual(result.evidence.relative_path, fixture.name)
        finally:
            fixture.close()

    def test_HASONLO_NEVU_testverfajl_NEM_lephet_be(self) -> None:
        """A forrás-prototípus szuffix-heurisztikája pontosan ezt tette — naplózva.

        Ha a „hasonló nevű" fájl becsúszhatna, a bizonyíték-lánc értelmét
        vesztené: a hash egy MÁSIK fájlé lenne, mint amiből az adat jött.
        """
        fixture = _PdfFixture([TARTALOM_LAP], name="irat.pdf")
        try:
            (fixture.root / "irat_v2.pdf").write_bytes(build_pdf([BELYEGZO_LAP]))
            reader = DocumentTextReader(fixture.config())

            eredeti = reader.read("irat.pdf")
            # A hasonlo nevu testver ONALLOAN mas eredmenyt ad -- tehat ha
            # valaha becsuszna, az MERHETO kulonbseget okozna.
            with self.assertRaises(SourceUnreadableError):
                reader.read("irat_v2.pdf")

            self.assertEqual(eredeti.evidence.relative_path, "irat.pdf")
            self.assertNotIn("irat_v2", eredeti.evidence.relative_path)
        finally:
            fixture.close()

    def test_a_gyokerbol_kivezeto_ut_ELBUKIK(self) -> None:
        """A hibatípus SZÁNDÉKOSAN `ConfigurationError`, nem `SourceUnreadableError`.

        A repó a kettőt következetesen szétválasztja: a `SourceUnreadableError`
        azt mondja, hogy **a fájlt** nézd meg, a `ConfigurationError` azt, hogy
        **a beállítást**. Egy gyökérből kivezető útvonal a hívó kérésének hibája,
        nem a forrásé — és ha a teszt itt a lazább közös őst fogadná el, épp azt
        a megkülönböztetést mosná el, ami miatt a két típus létezik.
        """
        from doccapture.core.errors import ConfigurationError

        fixture = _PdfFixture([TARTALOM_LAP])
        try:
            with self.assertRaises(ConfigurationError):
                DocumentTextReader(fixture.config()).read("../kivul.pdf")
        finally:
            fixture.close()


# ==========================================================================
# Útválasztás — a négy bemenet négy külön út
# ==========================================================================


class RoutingTests(unittest.TestCase):
    def test_a_NEM_szovegreteges_utra_jelolt_fajlt_kimondottan_elutasitja(self) -> None:
        fixture = _PdfFixture([TARTALOM_LAP], name="tabla.csv")
        try:
            with self.assertRaises(SourceUnreadableError) as ctx:
                DocumentTextReader(fixture.config()).read("tabla.csv")
            self.assertIn("tabular", str(ctx.exception))
        finally:
            fixture.close()

    def test_a_zaj_fajlt_kizarja(self) -> None:
        fixture = _PdfFixture([TARTALOM_LAP], name="~$irat.pdf")
        try:
            with self.assertRaises(SourceUnreadableError) as ctx:
                DocumentTextReader(fixture.config()).read("~$irat.pdf")
            self.assertIn("zaj-fájl", str(ctx.exception))
        finally:
            fixture.close()


if __name__ == "__main__":
    unittest.main()
