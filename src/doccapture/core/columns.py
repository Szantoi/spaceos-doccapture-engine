"""Elrendezés-szabályok: olvasási sorrend és hasáb-összeolvadás JELZÉSE.

Miért nem a `core/documents/` alá: az az irat-TÍPUS tengelye (mit jelent a
tartalom), ez az ELRENDEZÉS tengelye (hol áll a lapon). Mindkét olvasási út —
a szövegréteges MA, a raszteres KÉSŐBB — ugyanezt kéri, és két példány
elcsúszna egymástól.

MIT CSINÁL ÉS MIT NEM (M2 mai határa)
-------------------------------------
Szkennelt, hasábos elrendezésnél a szövegréteg gyakran EGY sorba olvasztja a
két hasábot. Ez a modul a gyanút **jelöli**, megnevezett indokkal — de NEM
vágja szét: ahol a hasábok egy futamban jönnek, a köztük lévő rés a szövegből
már elveszett, és az egyetlen megbízható vágópont a horgony-token — az viszont
profil-adat (M1), tehát egy itteni vágó-szabály két igazságot teremtene
ugyanarról. M2 állapota ezért: `részben` — a jelzés él, a szétvágás nincs.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import dataclass

from doccapture.core.layout import PageLayout, TextFragment
from doccapture.core.text_layer_options import TextLayerOptions


def reading_order(fragments: list[TextFragment]) -> list[TextFragment]:
    """Determinisztikus olvasási sorrend: fentről le, azon belül balról jobbra.

    A forrás-prototípus ezt modellre bízta — attól a sorrend futásonként
    változhatott, és minden későbbi lépés (sor-összerakás, horgony-keresés)
    nem-determinisztikus bemenetet kapott. Itt a szabály kimondott és gépi:
    `(y_top, x_left, y_bottom, x_right, text)` — az utolsó kulcsok döntetlen
    esetén is teljes rendezést adnak, tehát két azonos geometriájú futás
    azonos sorrendet ad. Ez közvetlen G2-nyereség (determinizmus).
    """
    return sorted(
        fragments,
        key=lambda f: (f.y_top, f.x_left, f.y_bottom, f.x_right, f.text),
    )


@dataclass(frozen=True)
class MergedColumnSuspicion:
    """Egy összeolvadás-gyanús fragmens, a gyanú MEGNEVEZETT okával.

    A `reason` embernek szól és kimondja a számokat: egy diagnosztika, ami
    csak annyit mond, hogy „gyanús", nem ellenőrizhető — a mérés attól
    bizonyíték, hogy megmondja, mit mért és mihez képest.
    """

    fragment: TextFragment
    span_ratio: float
    reason: str


def detect_merged_columns(
    page: PageLayout, options: TextLayerOptions
) -> list[MergedColumnSuspicion]:
    """A lapszélesség konfigurált hányadát átfogó fragmensek JELÖLÉSE.

    A küszöb (`options.merged_span_ratio`) domain-beállítás, nem beégetett
    érték: elrendezésenként más, mekkora vízszintes kiterjedés normális.
    A visszatérő lista üres, ha nincs gyanú — a hívó ebből tudja, hogy a
    detektor futott és nem szólt, ami MÁS, mint hogy nem futott.
    """
    suspicions: list[MergedColumnSuspicion] = []
    for fragment in page.fragments:
        span_ratio = (fragment.x_right - fragment.x_left) / page.width
        if span_ratio >= options.merged_span_ratio:
            suspicions.append(
                MergedColumnSuspicion(
                    fragment=fragment,
                    span_ratio=span_ratio,
                    reason=(
                        f"a fragmens a lapszélesség {span_ratio:.0%}-át fogja át "
                        f"(küszöb: {options.merged_span_ratio:.0%}) — hasábos "
                        f"forrásnál ez összeolvadt sorra utal (M2); a jelzés "
                        f"jelölés, nem szétvágás"
                    ),
                )
            )
    return suspicions
