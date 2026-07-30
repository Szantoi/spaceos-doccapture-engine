"""A `CaptureRecord` wire-alakja — a publikált szerződés szerint.

MIÉRT AZ INFRASTRUKTÚRÁBAN, NEM A MAGBAN
----------------------------------------
A **szerződés alakja** domain-döntés (a `contracts/` alatt publikált séma
hordozza), de a **szerializálás** infrastruktúra: JSON-ról, kulcs-nevekről és
kódolásról szól. Ha a magban lenne, a domain tudna a szállítási formátumról — és
onnantól nem cserélhető.

A HÁROM SZABÁLY, AMI ITT DÖNT
-----------------------------
1. **A wire nem árulja el, mi van mögötte.** Nincs benne belső típusnév, könyvtár-
   név, abszolút útvonal. Ha elárulná, a motor cserélhetetlen lenne.
2. **A bizonytalanság végigmegy.** Minden érték mellett megbízhatóság, indok és
   bizonyíték. A fogyasztó nem kaphat „csak az értéket".
3. **A dátum ISO-8601 sztring.** Platform-oldali könyvtár-választás nem kerül a
   wire-ra — a fogyasztó a `value_type`-ból tudja, hogy az a sztring dátum.

⚠ **A hash a wire-tartalmat fedi.** Ha ide új mező kerül, de a
`contracts/capture-record.schema.json`-ba nem, a `tests/test_contract.py`
**elbukik** — mindkét irányban. Ez nem konvenció, hanem kapu.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Mapping

from doccapture.core.models import CaptureRecord, Confidence, Extracted, SourceEvidence

CONTRACT_VERSION = "1.0.0"
"""A szerződés verziója. **Egy helyen**, és a séma `$id`-jével együtt emelendő.

A fogyasztó a **fő** verziót ellenőrzi: ismeretlen fő verzió esetén el kell
bukni, mert a törő változás különben csendben téves adatot ad. Additív
bővítésnél a középső szám nő.
"""


def record_to_wire(record: CaptureRecord) -> dict[str, Any]:
    """`CaptureRecord` → a publikált wire-alak.

    A `needs_human` **származtatott** mező. Kimegy a wire-ra kényelmi okból, de a
    premisszája — hogy **minden bemenete** (az összes érték megbízhatósága) is a
    wire-on van — nem feltevés: a `test_contract.py` **újraszámolja a wire-ból**,
    és összeveti. Enélkül a hash megszűnne identitás lenni arra a mezőre.
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "input_kind": record.input_kind.value,
        "evidence": _evidence_to_wire(record.evidence),
        "fields": {key: _extracted_to_wire(item) for key, item in record.fields.items()},
        "rows": [
            {key: _extracted_to_wire(item) for key, item in row.items()}
            for row in record.rows
        ],
        "diagnostics": list(record.diagnostics),
        "needs_human": record.needs_human,
    }


def _evidence_to_wire(evidence: SourceEvidence) -> dict[str, Any]:
    return {
        "relative_path": evidence.relative_path,
        "content_hash": evidence.content_hash,
        "locator": evidence.locator,
    }


def _extracted_to_wire(item: Extracted[Any]) -> dict[str, Any]:
    value, value_type = _value_to_wire(item.value)
    return {
        "value": value,
        "confidence": item.confidence.value,
        "value_type": value_type,
        "note": item.note,
        "evidence": _evidence_to_wire(item.evidence) if item.evidence else None,
    }


def _value_to_wire(value: Any) -> tuple[Any, str | None]:
    """Érték → `(wire-érték, wire-típus)`.

    A sorrend **nem véletlen**: a `bool` a Pythonban `int`, tehát ha a szám-ágat
    vizsgálnánk előbb, egy `True` **számként** menne ki a wire-ra — és a
    fogyasztó `1`-et látna egy logikai mező helyén.

    A `datetime` a `date` előtt: a `datetime` a `date` **altípusa**, tehát fordítva
    minden időpont csendben dátummá csonkolódna.
    """
    if value is None:
        # `missing` megbizhatosagnal nincs ertek, tehat a tipus sem levezetheto.
        return None, None
    if isinstance(value, bool):
        return value, "boolean"
    if isinstance(value, _dt.datetime):
        return value.date().isoformat(), "date"
    if isinstance(value, _dt.date):
        return value.isoformat(), "date"
    if isinstance(value, int):
        return value, "integer"
    if isinstance(value, float):
        return value, "number"
    return str(value), "text"


def recompute_needs_human(wire: Mapping[str, Any]) -> bool:
    """A `needs_human` újraszámolása **kizárólag a wire-ból**.

    Ez nem kényelmi függvény, hanem a **származtatott mező premisszájának
    mérőeszköze**: ha ez a számítás a wire-ból elvégezhető, akkor a mező minden
    bemenete a wire-on van, tehát a hash lefedi. Ha nem, a hash arra a mezőre
    megszűnt identitás lenni.

    Szándékosan **nem** a `CaptureRecord`-ból dolgozik — az ugyanaz az igazság
    lenne kétszer, és nem bizonyítana semmit.
    """
    confirmed = Confidence.CONFIRMED.value
    items = list(wire.get("fields", {}).values())
    for row in wire.get("rows", []):
        items.extend(row.values())
    return any(item.get("confidence") != confirmed for item in items)
