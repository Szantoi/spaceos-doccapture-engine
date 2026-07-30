"""Egy táblázat beolvasásának eredménye — a diagnosztikával EGYÜTT.

Miért külön modul, és nem a `ports.py`-ban: a közös összeállító logika
(`assembly.py`) is ezt a típust állítja elő, és ha a típus a `ports.py`-ban
lakna, körkörös import keletkezne (`ports` → `tabular` → `ports`). A körkörös
importot meg lehet trükközni késleltetéssel, de az elrejti a valódi kérdést:
**ez a típus a táblázatos úthoz tartozik, nem a portok készletéhez.**

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from doccapture.core.models import Confidence


@dataclass(frozen=True)
class TabularReadResult:
    """Egy táblázat beolvasásának TELJES eredménye.

    ⚠ **Ez a típus a DC-01b mérésének következménye, nem szépítés.** A port
    eredetileg csak sorokat adott vissza (`read_rows`), és amikor az első
    adaptert megépítettük, kiderült, hogy akkor az adapternek **el kell dobnia**
    az illesztetlen fejléceket, a kihagyott üres sorok számát, a fejlécből
    felismert mértékegységeket és a gyorsítótár-hiányt.

    Egy port, ami a diagnosztika eldobására kényszerít, **csendes adatvesztést
    tervez be**: ha nincs hova írni, akkor nem lesz megírva — és a betöltés
    hiánytalannak fog látszani.
    """

    rows: list[dict[str, Any]] = field(default_factory=list)
    """Sorok: belső kulcs → `Extracted`. A kulcs a séma kulcsa, nem a fejléc szövege."""

    units: dict[str, str] = field(default_factory=dict)
    """Belső kulcs → a fejlécből felismert mértékegység. Megőrizve, NEM átváltva (M15)."""

    diagnostics: list[str] = field(default_factory=list)
    """Amit észrevettünk, de nem javítottunk. Ember számára olvasható."""

    header_evidence_locator: str = ""
    """Hol volt a fejléc-sor (pl. `Munka1!R1`) — a mértékegység bizonyítéka."""

    skipped_blank_rows: int = 0
    """Üresként kihagyott sorok száma.

    **Megszámolva**, mert a prototípus itt némán dobott sorokat (`if desc:`), és
    nem lehetett megtudni, hogy 0-t vagy 40-et hagyott ki.
    """

    unmatched_headers: tuple[tuple[int, str], ...] = ()
    """(index, nyers fejléc) — a fájlban van, a sémában nincs.

    Nem hiba, de kimondjuk: ha épp egy elgépelt fejléc miatt nem illeszkedett
    valami, az CSAK itt látszik.
    """

    missing_optional_keys: tuple[str, ...] = ()
    """Nem kötelező oszlopok, amik ebben a fájlban nincsenek meg."""

    truncated: bool = False
    """Igaz, ha a sor-korlát miatt NEM olvastuk végig a fájlt.

    Külön mező és nem csak diagnosztika-szöveg: erre a fogyasztónak **dönteni**
    kell tudni, és egy szabad szöveget nem fog kiértékelni. Egy néma csonkolás
    pontosan úgy néz ki, mint egy hiánytalan betöltés.
    """

    @property
    def needs_human(self) -> bool:
        """Igaz, ha bármi emberi szemet kíván — egyetlen bizonytalan cella is elég.

        Nem átlagolunk: egy 5000 soros betöltésben egy hibás sor átlagolva
        eltűnik, pedig épp az az egy sor a lényeg.
        """
        return any(
            item.confidence is not Confidence.CONFIRMED
            for row in self.rows
            for item in row.values()
        )
