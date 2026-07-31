"""Lap-geometria modelljei — szövegréteges ÉS raszteres bemenethez közös.

Külön modulban, nem a `models.py`-ban: a `models.py` a motor KÉT ALAPSZABÁLYÁT
hordozza (bizonytalanság + bizonyíték-lánc), és azt nem hígítjuk geometriával.

EGY MÉRTÉKEGYSÉG — ÉS MIÉRT ITT ÁLL A SZABÁLY, NEM AZ ADAPTERBEN
----------------------------------------------------------------
A geometria ebben a modellben MINDIG tipográfiai pontban van (1/72 hüvelyk),
az origó a lap BAL-FELSŐ sarka, és az y lefelé nő. Ez nem ízlés, hanem mért
kényszer: a szövegréteg-olvasó könyvtár **alul-nullás** koordinátát ad (mérve:
a lap aljától számol), a raszter-út felül-nullásat — ha a szabály az adapterben
élne, a második adapter csendben megfordítana mindent. A konverzió az adapter
dolga, a SZABÁLY a domainé, és az invariáns itt buktatja el a konvertálatlan
adatot: alul-nullás rendszerben a „tető" számértéke NAGYOBB, mint az „aljáé",
tehát a nyers átvétel `y_top > y_bottom`-ot ad — pontosan ezt fogja meg a
`__post_init__`.

A raszteres eredet (hány DPI-s képből jött a lap) **provenancia-adat**
(`PageLayout.source_dpi`), nem alternatív reprezentáció. A „dpi VAGY pont"
kettősség egy mező két jelentése lenne — ugyanaz a hibaosztály, amit az
opcionális `x_right`-nál elutasítottunk.

MIÉRT float ÉS MIÉRT KÖTELEZŐ AZ `x_right`
------------------------------------------
- **float:** a lapméret pontban tört szám (mérve: A4 = 595.276 × 841.89 pont) —
  int-ben nem tárolható, a kerekítés pedig néma torzítás lenne.
- **`x_right` kötelező:** a jobb szél ugyanabból a könyvtár-hívásból ingyen
  megvan (mérve: a rect mind a négy sarka egyszerre jön) — az elhagyása nem
  takarékosság, hanem adósság-teremtés. A forrás-prototípus mindhárom
  felismerő-adaptere eldobta az x-maximumot, és utólag pótolhatatlan.

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

    A geometria pontban, bal-felső origóval — ld. a modul-docstringet.
    """

    text: str
    raw_confidence: float

    x_left: float
    y_top: float
    x_right: float
    y_bottom: float

    def __post_init__(self) -> None:
        """A geometriai invariáns a DOMAINBEN bukik, nem az adapterben.

        `x_left < x_right` és `y_top < y_bottom` — egy nulla-szélességű vagy
        fordított téglalap nem mérési pontatlanság, hanem konverziós hiba
        (tipikusan: az alul-nullás forrás-koordináta nyers átvétele), és ott
        kell elbuknia, ahol keletkezik.
        """
        if not self.x_left < self.x_right:
            raise ValueError(
                f"TextFragment: x_left ({self.x_left}) < x_right ({self.x_right}) "
                f"kell legyen — fordított vagy nulla-szélességű téglalap konverziós hiba."
            )
        if not self.y_top < self.y_bottom:
            raise ValueError(
                f"TextFragment: y_top ({self.y_top}) < y_bottom ({self.y_bottom}) "
                f"kell legyen. Ha a forrás alul-nullás (a lap aljától számol), a "
                f"nyers átvétel pont ezt az alakot adja — az adapternek konvertálnia kell."
            )


@dataclass
class PageLayout:
    """Egy lap tartalma a feldolgozás közbeni állapotával.

    A `source_name` a bemeneti gyökérhez képest relatív — abszolút út itt sem
    tárolható, ugyanaz az elv, mint a `SourceEvidence`-ben.

    A `width`/`height` pontban (ld. a modul-docstringet). A `source_dpi` a
    raszteres eredet PROVENANCIÁJA: megmondja, milyen felbontású képből jött a
    lap, de a geometria attól még pontban van — nem alternatív mértékegység.
    Szövegréteges forrásnál `None`.
    """

    source_name: str
    width: float
    height: float
    fragments: list[TextFragment] = field(default_factory=list)
    source_dpi: Optional[float] = None

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError(
                f"PageLayout: a lapméret pozitív pont-érték kell legyen "
                f"(width={self.width}, height={self.height})."
            )
        if self.source_dpi is not None and self.source_dpi <= 0:
            raise ValueError(
                f"PageLayout: a source_dpi provenancia-adat pozitív kell legyen, "
                f"{self.source_dpi!r} nem az."
            )
