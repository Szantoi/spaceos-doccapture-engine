"""Irat-profilok: mi az irat, és mit kérünk tőle.

A `tabular` alcsomag párja, másik tengelyen:

| Alcsomag | Tengely | Mit mond meg |
|---|---|---|
| `core.tabular` | **hogyan olvassuk** | oszlop-térképezés, érték-értelmezés |
| `core.documents` | **mi az irat** | típus-felismerés, mezők, önellenőrző számtan |

| Modul | Felelősség |
|---|---|
| `profile.py` | a profil-típusok (`DocumentProfile`, `FieldSpec`, `ConsistencyRule`) — **adat, nem kód** |
| `detect.py` | típus-felismerés **horgony-bizonyítékkal**; holtversenynél nem dönt |
| `extract.py` | címke → érték szövegsorokból, determinisztikusan |
| `consistency.py` | M3 (jelöl, nem javít) + M4 (a hibára kevésbé érzékeny út) |

Az érték-értelmezés **ugyanaz**, mint a táblázatos úton (`core.tabular.values`) —
ha kettő lenne, az egyik előbb-utóbb elcsúszna.
"""

from __future__ import annotations

from doccapture.core.documents.consistency import RuleOutcome, apply_rules
from doccapture.core.documents.detect import (
    DetectionResult,
    ProfileMatch,
    detect_profile,
    normalize_text,
)
from doccapture.core.documents.extract import extract_fields
from doccapture.core.documents.profile import (
    ConsistencyRule,
    DocumentProfile,
    FieldSpec,
    Operation,
)

__all__ = [
    "ConsistencyRule",
    "DetectionResult",
    "DocumentProfile",
    "FieldSpec",
    "Operation",
    "ProfileMatch",
    "RuleOutcome",
    "apply_rules",
    "detect_profile",
    "extract_fields",
    "normalize_text",
]
