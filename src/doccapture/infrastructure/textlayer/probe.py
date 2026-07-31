"""A szövegréteg MÉRÉSE: van-e, és használható-e (háromállapotú verdikt).

MIÉRT KÜLÖN MODUL A READERTŐL
-----------------------------
Ez a mérés az **útválasztás bemenete**: eldönti, hogy a dokumentum a
szövegréteges vagy a raszteres úton megy tovább. Egy útválasztási döntés
bemenetének **önállóan futtathatónak** kell lennie — különben a bevezetéskor
nem lehet megnézni egy ügyfél 200 fájljáról, melyik melyik útra menne, anélkül,
hogy mindet végig is olvasnánk.

A MÉRT CSAPDA, AMI MIATT HÁROM ÁLLAPOT VAN
------------------------------------------
Egy szkennelt lapon, amin csak a szkenner lábléc-bélyegzője van, a szövegréteg
**22 karaktert ad 1 téglalapban**. Egy `count_chars > 0` boolean ezt a bélyegzőt
dokumentum-tartalomnak minősítené: a lap a szövegréteges úton menne tovább, a
valódi tartalma (a kép) pedig csendben elveszne — és a kimenet úgy nézne ki,
mint egy sikeres olvasás.

Ezért a verdikt három állapotú, és mindegyik **indokot** hordoz:

| Verdikt | Mit jelent | Mit tegyen a hívó |
|---|---|---|
| `USABLE` | elég érdemi karakter | mehet a szövegréteges úton |
| `AMBIGUOUS` | van szöveg, de kevés | **fail-closed**: kimondott hiány vagy hiba |
| `ABSENT` | gyakorlatilag üres | a raszteres út következik (DC-03) |

⚠ Ez a modul **dokumentumot nyit**, tehát infrastruktúra — a magban nem lehet.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from doccapture.core.errors import SourceUnreadableError
from doccapture.core.text_layer_options import TextLayerOptions


class TextLayerVerdict(str, Enum):
    """A szövegréteg használhatósága. Három állapot, mert kettő kevés."""

    USABLE = "usable"
    AMBIGUOUS = "ambiguous"
    ABSENT = "absent"


@dataclass(frozen=True)
class PageProbe:
    """Egy lap mérési eredménye."""

    page_number: int
    """1-alapú lapszám — a hívó és az ember ugyanazt a számot lássa."""

    char_count: int
    """Érdemi (nem üresköz) karakterek száma. Az üresköz szándékosan nem
    számít: egy csupa szóközből álló réteg nem tartalom."""

    rect_count: int
    """Szöveg-téglalapok száma. A karakterszám mellett azért kell, mert
    megkülönbözteti a bélyegzőt (sok karakter, 1 rect) a valódi tartalomtól."""

    width: float
    height: float
    """A lap mérete pontban."""


@dataclass(frozen=True)
class TextLayerMeasurement:
    """A teljes dokumentum mérése — verdikt + INDOK.

    Az indok nem díszítés: egy verdikt, ami csak annyit mond, hogy „nem
    használható", nem ellenőrizhető. A mérés attól bizonyíték, hogy megmondja,
    **mit** mért és **mihez képest**.
    """

    verdict: TextLayerVerdict
    reason: str
    page_count: int
    total_chars: int
    total_rects: int
    pages: tuple[PageProbe, ...]

    @property
    def usable(self) -> bool:
        """Csak a `USABLE` az igen. A kétértelmű **nem** csúszik át igenbe.

        Ez a fail-closed irány: a fordított hiba (kétértelműt igennek venni)
        **csendben téves** eredményt ad, ez az irány pedig **kimondott hiányt**.
        """
        return self.verdict is TextLayerVerdict.USABLE


def measure_text_layer(path: Path, options: TextLayerOptions) -> TextLayerMeasurement:
    """Megméri egy dokumentum szövegrétegét, lapról lapra.

    A küszöb **laponként** értendő: elég egyetlen használható lap ahhoz, hogy a
    dokumentum a szövegréteges úton menjen — a lapok közti eltérést (vegyes,
    részben szkennelt dokumentum) a diagnosztika mondja ki, nem hallgatja el.
    """
    options.validate()
    pdfium = _require_pdfium()

    pages: list[PageProbe] = []
    try:
        document = pdfium.PdfDocument(str(path))
    except Exception as exc:  # a konyvtar sajat hibatipusai nem szivarognak ki
        raise SourceUnreadableError(
            f"A dokumentum nem nyitható meg: {path.name} ({type(exc).__name__})"
        ) from exc

    try:
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            try:
                rect_count = text_page.count_rects()
                # A karaktereket a rectekbol olvassuk ossze, es az uresközt
                # kiszurjuk: egy csupa szokozbol allo reteg nem tartalom, de a
                # `count_chars` megszamolna.
                chars = 0
                for rect_index in range(rect_count):
                    rect = text_page.get_rect(rect_index)
                    chars += len(
                        "".join(text_page.get_text_bounded(*rect).split())
                    )
                pages.append(
                    PageProbe(
                        page_number=index + 1,
                        char_count=chars,
                        rect_count=rect_count,
                        width=float(page.get_width()),
                        height=float(page.get_height()),
                    )
                )
            finally:
                text_page.close()
                page.close()
    finally:
        document.close()

    return _verdict_for(pages, options)


def _verdict_for(
    pages: list[PageProbe], options: TextLayerOptions
) -> TextLayerMeasurement:
    """A lap-mérésekből a dokumentum-szintű verdikt, kimondott indokkal."""
    total_chars = sum(p.char_count for p in pages)
    total_rects = sum(p.rect_count for p in pages)
    usable_pages = [p for p in pages if p.char_count >= options.min_usable_chars_per_page]
    ambiguous_pages = [
        p
        for p in pages
        if options.ambiguous_chars_band
        <= p.char_count
        < options.min_usable_chars_per_page
    ]

    if not pages:
        return TextLayerMeasurement(
            verdict=TextLayerVerdict.ABSENT,
            reason="a dokumentumnak nincs egyetlen lapja sem",
            page_count=0,
            total_chars=0,
            total_rects=0,
            pages=(),
        )

    if usable_pages:
        reason = (
            f"{len(usable_pages)}/{len(pages)} lap éri el a küszöböt "
            f"({options.min_usable_chars_per_page} érdemi karakter/lap); "
            f"összesen {total_chars} karakter {total_rects} téglalapban"
        )
        if len(usable_pages) < len(pages):
            # A vegyes dokumentumot KIMONDJUK. Egy reszben szkennelt iratnal a
            # szovegreteges ut a szkennelt lapokrol semmit nem ad -- ha ezt
            # elhallgatnank, a hianyzo lapok ugy neznenek ki, mint ures lapok.
            reason += (
                f". ⚠ VEGYES dokumentum: {len(pages) - len(usable_pages)} lap "
                f"a küszöb alatt — azokról ez az út nem ad tartalmat"
            )
        return TextLayerMeasurement(
            verdict=TextLayerVerdict.USABLE,
            reason=reason,
            page_count=len(pages),
            total_chars=total_chars,
            total_rects=total_rects,
            pages=tuple(pages),
        )

    if ambiguous_pages:
        return TextLayerMeasurement(
            verdict=TextLayerVerdict.AMBIGUOUS,
            reason=(
                f"van szövegréteg, de egyetlen lap sem éri el a küszöböt "
                f"({options.min_usable_chars_per_page} érdemi karakter/lap); "
                f"a legtöbb egy lapon: {max(p.char_count for p in pages)} karakter "
                f"{max(p.rect_count for p in pages)} téglalapban. Ez tipikusan "
                f"szkenner-bélyegző vagy fejléc egy képlapon — NEM dokumentum-tartalom"
            ),
            page_count=len(pages),
            total_chars=total_chars,
            total_rects=total_rects,
            pages=tuple(pages),
        )

    return TextLayerMeasurement(
        verdict=TextLayerVerdict.ABSENT,
        reason=(
            f"{len(pages)} lap, összesen {total_chars} érdemi karakter — "
            f"gyakorlatilag nincs szövegréteg; a tartalom raszteres (felismerő út)"
        ),
        page_count=len(pages),
        total_chars=total_chars,
        total_rects=total_rects,
        pages=tuple(pages),
    )


def _require_pdfium() -> Any:
    """A szövegréteg-olvasás külső csomagot igényel — ezt kimondva kérjük.

    Miért nem a modul fejlécében importáljuk: az egész motort telepíthetetlenné
    tenné annak, akinek csak a táblázatos vagy a szöveges út kell. A mag
    `dependencies = []` marad, és ez piaci előny — ne dobjuk el egy import miatt.
    """
    try:
        import pypdfium2  # noqa: PLC0415 - szandekosan kesleltetett import
    except ImportError as exc:  # pragma: no cover - telepitesi kerdes
        raise SourceUnreadableError(
            "A szövegréteg-olvasáshoz a `document` extra kell: "
            "`pip install doccapture-engine[document]`. A táblázatos és a "
            "szöveges út ettől függetlenül működik."
        ) from exc
    return pypdfium2
