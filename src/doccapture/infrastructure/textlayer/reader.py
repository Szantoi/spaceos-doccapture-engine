"""`TextLayerReader` adapter: a beágyazott szövegréteg kiolvasása geometriával.

Ez az EGYETLEN hely a szövegréteges úton, ahol a könyvtár neve szerepel — a
port (`core/ports.py`) nem tud róla, és a use-case sem.

A KOORDINÁTA-KONVERZIÓ, MÉRVE — ÉS AMIT EGY INVARIÁNS NEM FOG MEG
------------------------------------------------------------------
A könyvtár **alul-nullás** koordinátát ad: a `get_rect(i)` négyese
`(x_bal, y_ALSÓ, x_jobb, y_FELSŐ)`, ahol az y a lap **aljától** nő. Mérve, egy
kézzel írt fixture-ön (a lap 841.89 pont magas, a szöveg alulról y=700-ra írva):

```
get_rect(0) = (72.876, 699.868, 176.880, 708.592)
```

A domain viszont **bal-felső origójú**, y lefelé nő (`core/layout.py`). A helyes
konverzió tehát:

```
x_left  = rect[0]                 y_top    = lapmagasság - rect[3]
x_right = rect[2]                 y_bottom = lapmagasság - rect[1]
```

⚠ **Két különböző elrontási mód van, és az invariáns csak az egyiket fogja meg:**

1. **Név szerinti naiv átvétel** (`y_top = rect[3]`, mert az a „felső"):
   ilyenkor `y_top > y_bottom`, és a `TextFragment.__post_init__` **elbukik**.
   Ezt az invariáns megfogja.
2. **Index szerinti naiv átvétel** (`y_top = rect[1]`, `y_bottom = rect[3]`):
   ilyenkor `y_top < y_bottom` **teljesül**, tehát az invariáns **átengedi** —
   pedig a lap fejjel lefelé áll. Ezt csak a **tényleges pozíció** kimérése
   fogja meg (a fenti fixture-ön a helyes `y_top` ≈ 133.3, nem ≈ 699.9).

Ezért a kapu-készlet nem elégszik meg az invariánssal: a teszt a *várt
koordinátát* méri, nem csak a reláció fennállását. (Ugyanaz a tanulság, mint a
megengedő teszteknél: egy feltétel, ami a hibás alakra is teljesül, nem kapu.)

NAPLÓ-HIGIÉNIA
--------------
Darabszám és szerkezet igen; fragmens-TARTALOM és abszolút út **soha**. Amit
kiírunk, az a hibakereséshez elég (hány lap, hány fragmens, relatív út), és
nem visz ki üzleti adatot egy olyan fájlba, aminek lazább a védelme.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.layout import PageLayout, TextFragment
from doccapture.core.observability import get_logger, log_step
from doccapture.core.ports import TextLayerReader
from doccapture.infrastructure.evidence import resolve_source
from doccapture.infrastructure.textlayer.probe import measure_text_layer

_log = get_logger("textlayer")

# A szovegreteges forrasnal nincs felismeres, tehat nincs mit "nyersen
# megbizhatonak" minositeni: a karakterek a dokumentumban ALLNAK, nem
# tippeltuk oket. Az 1.0 itt nem optimizmus, hanem annak kimondasa, hogy ezen
# az uton a felismeres-bizonytalansag NEM ertelmezett. (A domain `Confidence`
# ettol fuggetlen: azt az uzleti ellenorzes donti el, nem ez a szam.)
_TEXT_LAYER_RAW_CONFIDENCE = 1.0


class PdfiumTextLayerReader(TextLayerReader):
    """`TextLayerReader` digitális dokumentumok beágyazott szövegrétegéhez."""

    ADAPTER_NAME = "textlayer"

    def __init__(self, config: Optional[CaptureConfig] = None) -> None:
        self._config = config or CaptureConfig()
        self._config.text_layer.validate()

    def has_text_layer(self, relative_path: str) -> bool:
        """A probe verdiktjéből SZÁRMAZIK — nem külön szabályból.

        Ha ez saját küszöböt tartana, két igazság lenne ugyanarról a döntésről,
        és az egyik előbb-utóbb hazudna. A `usable` szándékosan csak a
        `USABLE`-re igaz: a kétértelmű eset nem csúszik át igenbe.
        """
        path = resolve_source(self._config.input_root, relative_path)
        measurement = measure_text_layer(path, self._config.text_layer)
        log_step(
            _log,
            "textlayer.probe",
            source=relative_path,
            verdict=measurement.verdict.value,
            pages=measurement.page_count,
            chars=measurement.total_chars,
            rects=measurement.total_rects,
        )
        return measurement.usable

    def read_pages(self, relative_path: str) -> list[PageLayout]:
        """A szövegréteg kiolvasása lapokra bontva, pont-egységű geometriával.

        A forrást csak OLVASSUK (M10) — semmit nem írunk mellé.
        """
        pdfium = _require_pdfium()
        path = resolve_source(self._config.input_root, relative_path)

        try:
            document = pdfium.PdfDocument(str(path))
        except Exception as exc:
            raise SourceUnreadableError(
                f"A dokumentum nem nyitható meg: {path.name} ({type(exc).__name__})"
            ) from exc

        pages: list[PageLayout] = []
        try:
            for index in range(len(document)):
                pages.append(self._read_page(document, index, relative_path))
        finally:
            document.close()

        log_step(
            _log,
            "textlayer.read",
            source=relative_path,
            pages=len(pages),
            fragments=sum(len(p.fragments) for p in pages),
        )
        return pages

    # ------------------------------------------------------------------

    def _read_page(self, document: Any, index: int, relative_path: str) -> PageLayout:
        """Egy lap kiolvasása. A konverzió itt történik, egy helyen."""
        page = document[index]
        try:
            height = float(page.get_height())
            width = float(page.get_width())
            text_page = page.get_textpage()
            try:
                fragments: list[TextFragment] = []
                for rect_index in range(text_page.count_rects()):
                    x_left, y_low, x_right, y_high = text_page.get_rect(rect_index)
                    text = text_page.get_text_bounded(x_left, y_low, x_right, y_high)
                    if not text.strip():
                        # Ures teglalap nem fragmens. Nem hallgatjuk el: a
                        # darabszam-kulonbseg a naploban latszik.
                        continue
                    fragments.append(
                        TextFragment(
                            text=text,
                            raw_confidence=_TEXT_LAYER_RAW_CONFIDENCE,
                            x_left=float(x_left),
                            # ALUL-NULLASBOL BAL-FELSOBE. A lap tetejetol mert
                            # tavolsag a lapmagassag minusz a felso el.
                            y_top=height - float(y_high),
                            x_right=float(x_right),
                            y_bottom=height - float(y_low),
                        )
                    )
            finally:
                text_page.close()
        finally:
            page.close()

        # A `source_name` a lapot azonositja a forrason belul, RELATIV uttal --
        # abszolut ut itt sem tarolhato (ugyanaz az elv, mint a bizonyitekban).
        return PageLayout(
            source_name=f"{relative_path}#{index + 1}",
            width=width,
            height=height,
            fragments=fragments,
        )


def _require_pdfium() -> Any:
    """Ld. a `probe._require_pdfium` indoklását — ugyanaz a kimondott kérés."""
    try:
        import pypdfium2  # noqa: PLC0415 - szandekosan kesleltetett import
    except ImportError as exc:  # pragma: no cover - telepitesi kerdes
        raise SourceUnreadableError(
            "A szövegréteg-olvasáshoz a `document` extra kell: "
            "`pip install doccapture-engine[document]`. A táblázatos és a "
            "szöveges út ettől függetlenül működik."
        ) from exc
    return pypdfium2
