"""Raszteres bemenet elrendezés-modelljei.

Külön modulban, nem a `models.py`-ban: a `models.py` a motor KÉT ALAPSZABÁLYÁT
hordozza (bizonytalanság + bizonyíték-lánc), és azt nem hígítjuk geometriával.
Ezek a típusok csak akkor kellenek, ha van mit elhelyezni a lapon — táblázatos
vagy szövegréteges bemenetnél nincs.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TextFragment:
    """Egy összefüggő szövegdarab a lapon, a felismerés nyers megbízhatóságával.

    A `raw_confidence` a FELISMERŐ saját pontszáma (0.0-1.0) — szándékosan NEM
    azonos a domain `Confidence` szintjeivel. A kettő összemosása lenne a
    leggyakoribb hiba: egy 0.91-es OCR-pontszám nem jelenti, hogy az érték
    `CONFIRMED` — azt az üzleti ellenőrzés (pl. redundancia) döntheti el.
    A leképzés a fázisok dolga, és mindig kimondott.
    """

    text: str
    raw_confidence: float

    x_left: int
    y_top: int
    y_bottom: int
    x_right: Optional[int] = None


@dataclass
class PageLayout:
    """Egy lap tartalma a feldolgozás közbeni állapotával.

    A `source_name` a bemeneti gyökérhez képest relatív — abszolút út itt sem
    tárolható, ugyanaz az elv, mint a `SourceEvidence`-ben.
    """

    source_name: str
    width: int
    height: int
    fragments: list[TextFragment] = field(default_factory=list)
