"""Domain-modellek — a motor két alapszabálya kódban.

1. A bizonytalanság ADAT, nem hiba: minden kinyert érték megbízhatósági szintet
   hordoz. "Inkább hiány, mint téves" — a csendes tévedés drágább, mint a
   bevallott hiány, mert a bevallott hiányt valaki megnézi.

2. Minden érték VISSZAVEZETHETŐ a forrására: relatív útvonal + tartalom-hash.
   Egy későbbi eltérésnél így eldönthető, a forrás változott-e vagy a kinyerés.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, Optional, TypeVar


class Confidence(str, Enum):
    """Egy kinyert érték megbízhatósága.

    A fogyasztó ebből tudja eldönteni, mit tehet automatikusan és mit kell
    emberrel jóváhagyatni. A `MISSING` NEM hiba-állapot: az a helyes válasz
    akkor, amikor nem tudjuk biztosan — a tippelés a hiba.
    """

    CONFIRMED = "confirmed"
    """Ellenőrzött vagy redundanciával megerősített érték."""

    NEEDS_REVIEW = "needs_review"
    """Kiolvastuk, de valami gyanús — emberi szem kell rá."""

    MISSING = "missing"
    """Nem tudtuk kiolvasni. Szándékosan üres, nem kitalált."""


class InputKind(str, Enum):
    """A négy bemenet NÉGY külön út — összemosni tervezési hiba.

    A tabellás és a szövegréteges bemenet determinisztikusan feldolgozható:
    ott modellt használni fölösleges költség és fölösleges kockázat.
    """

    TABULAR = "tabular"
    """Táblázatos fájl. Parse, nem OCR. Modell nem kell."""

    TEXT_LAYER_DOCUMENT = "text_layer_document"
    """Beágyazott szövegréteggel rendelkező dokumentum. Modell nem kell."""

    RASTER_SCAN = "raster_scan"
    """Szkennelt/fotózott raszter. Szövegréteg-előállítás kell."""

    HANDWRITING = "handwriting"
    """Kézírás. Vizuális átirat, mindig bizonytalanság-jelzéssel."""


@dataclass(frozen=True)
class SourceEvidence:
    """Honnan jött az érték — a bizonyíték-lánc egy szeme.

    A `content_hash` teszi eldönthetővé, hogy egy későbbi eltérésnél a forrás
    változott-e meg vagy a kinyerésünk. Útvonal önmagában erre nem elég.
    """

    relative_path: str
    """A forrásfájl útvonala a bemeneti gyökérhez képest. Abszolút út nem tárolható."""

    content_hash: str
    """A forrásfájl tartalmának hashe (hex)."""

    locator: Optional[str] = None
    """Hely a forráson belül, ha értelmezhető (lap, oldal, cella, sor)."""


T = TypeVar("T")


@dataclass(frozen=True)
class Extracted(Generic[T]):
    """Egy kinyert érték a megbízhatóságával és a bizonyítékával együtt.

    Szándékosan nincs `.value_or_default()` kényelmi metódus: aki az értéket
    használja, lássa a megbízhatóságot is. A kényelem itt hibaforrás lenne.
    """

    value: Optional[T]
    confidence: Confidence
    evidence: Optional[SourceEvidence] = None
    note: Optional[str] = None
    """Miért nem CONFIRMED — ember számára olvasható indok."""

    def __post_init__(self) -> None:
        if self.confidence is Confidence.MISSING and self.value is not None:
            raise ValueError("MISSING megbízhatóság mellett nem lehet érték.")
        if self.confidence is not Confidence.MISSING and self.value is None:
            raise ValueError("Érték nélküli állítás megbízhatósága csak MISSING lehet.")


@dataclass
class CaptureRecord:
    """Egy forrásból kinyert, még NEM értelmezett adathalmaz.

    A motor eddig jut el: megmondja, mi van a papíron. Azt NEM, hogy mi
    kerüljön a fogadó rendszerbe — a párosítás és az átváltás a fogyasztóé.
    """

    input_kind: InputKind
    evidence: SourceEvidence
    fields: dict[str, Extracted[Any]] = field(default_factory=dict)
    rows: list[dict[str, Extracted[Any]]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    """Amit a motor észrevett, de nem javított — pl. felbomló redundancia."""

    @property
    def needs_human(self) -> bool:
        """Igaz, ha bármi emberi szemet kíván. A hívó ne számolja újra."""
        candidates = list(self.fields.values()) + [
            value for row in self.rows for value in row.values()
        ]
        return any(item.confidence is not Confidence.CONFIRMED for item in candidates)
