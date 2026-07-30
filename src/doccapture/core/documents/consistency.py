"""Önellenőrző számtan az iraton — M3 és M4 együtt.

M3 — A REDUNDANCIA INGYEN ELLENŐRZÉS
------------------------------------
Az üzleti iratok tele vannak önellenőrző számtannal: tétel-érték = mennyiség ×
egységár; végösszeg = adóalap + adó; összes idő = a művelet-idők összege. Ez
**ingyen** ellenőrzés: nem kell hozzá külső forrás, csak észre kell venni.

Ha nem stimmel (tűréssel), **jelölünk, nem javítunk csendben** — és a
diagnosztika **megnevezi, MELYIK egyenlőség bomlott el**. Ez a lényeg: a hiba
abból **visszafejthető**. Egy „valami nem stimmel" jelzés használhatatlan; egy
„a tétel-érték nem egyezik a mennyiség × egységárral, eltérés 240" megmondja,
hol keresd.

M4 — A HIBÁRA LEGKEVÉSBÉ ÉRZÉKENY BEMENET
-----------------------------------------
Ha ugyanaz az érték több úton is kiszámolható, azt az utat vedd, amelyik **nem
függ a törékeny mezőtől**. Gyakorlatban: ha a mennyiség olvasása bizonytalan, de
az egységár és a tétel-érték biztos, akkor a mennyiséget **azokból** számoljuk.

A származtatott érték **soha nem `CONFIRMED`** — `NEEDS_REVIEW`, és a
megjegyzés kimondja, **honnan** jött. Egy származtatott érték, ami
megkülönböztethetetlen a leolvasottól, csendes tévedés.

⚠ AHOL EZ A RÉTEG MEGÁLL
------------------------
A számtan azt vizsgálja, hogy **az irat önmagában stimmel-e**. Azt **nem**, hogy
mi kerüljön a fogadó rendszerbe — cikkszám-párosítás, mennyiség-átváltás,
jóváhagyás **nincs itt**, és nem is lesz (G1/G2 határ).

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from doccapture.core.models import Confidence, Extracted
from doccapture.core.documents.profile import ConsistencyRule, Operation

# A nullaval osztas hataraahoz. Nem "kicsi szam", hanem a lebegopontos abrazolas
# legkisebb ertelmes lepese -- ezert szamitott konstans, nem beirt szam.
_NEAR_ZERO = 1e-12


@dataclass(frozen=True)
class RuleOutcome:
    """Egy szabály kimenete — ember és gép számára is olvasható."""

    rule_name: str
    status: str
    """`ok` · `eltérés` · `származtatva` · `nem futott`"""

    detail: str
    """Miért ez a kimenet. Ez kerül a diagnosztikába."""

    @property
    def is_violation(self) -> bool:
        return self.status == "eltérés"


def apply_rules(
    fields: dict[str, Extracted[Any]],
    rules: tuple[ConsistencyRule, ...],
    default_tolerance: float,
) -> tuple[dict[str, Extracted[Any]], list[RuleOutcome]]:
    """A szabályok alkalmazása. Visszaad: (frissített mezők, kimenetek).

    A bemeneti szótárat **nem** módosítjuk: másolattal dolgozunk, mert a hívónak
    joga van látni, mi volt az olvasott állapot a származtatás előtt.

    A szabályok **sorrendben** futnak, és a származtatott érték a következő
    szabály bemenete lehet. Ez szándékos: egy iraton a végösszegből
    visszaszámolt adóalap egy másik egyenlőség operandusa lehet.
    """
    result = dict(fields)
    outcomes: list[RuleOutcome] = []

    for rule in rules:
        tolerance = default_tolerance if rule.tolerance is None else rule.tolerance
        outcomes.append(_apply_one(result, rule, tolerance))

    return result, outcomes


def _apply_one(
    fields: dict[str, Extracted[Any]], rule: ConsistencyRule, tolerance: float
) -> RuleOutcome:
    left = _numeric(fields.get(rule.left))
    operands = {key: _numeric(fields.get(key)) for key in rule.operands}
    missing_operands = [key for key, value in operands.items() if value is None]

    # --- 1. Mindketto ismert -> ELLENORZUNK (M3) ---
    if left is not None and not missing_operands:
        right = _combine(list(operands.values()), rule.operation)  # type: ignore[arg-type]
        delta = abs(left - right)
        if delta > tolerance:
            # JELOLUNK, nem javitunk. Es megnevezzuk, MELYIK egyenloseg bomlott el.
            fields[rule.left] = _flag(
                fields[rule.left],
                f"{rule.name}: az egyenlőség nem áll — bal={_fmt(left)}, "
                f"jobb={_fmt(right)}, eltérés={_fmt(delta)} (tűrés {_fmt(tolerance)}). "
                f"NEM javítottuk: a helyes érték üzleti döntés.",
            )
            for key in rule.operands:
                fields[key] = _flag(
                    fields[key], f"{rule.name}: érintett a bomló egyenlőségben"
                )
            return RuleOutcome(
                rule.name,
                "eltérés",
                f"{rule.left}={_fmt(left)} vs {_operation_text(rule)}={_fmt(right)}, "
                f"eltérés {_fmt(delta)} > tűrés {_fmt(tolerance)}",
            )
        return RuleOutcome(
            rule.name, "ok", f"{rule.left} egyezik ({_fmt(left)}, eltérés {_fmt(delta)})"
        )

    if not rule.derive:
        return RuleOutcome(
            rule.name, "nem futott", "hiányzó érték, és a származtatás kikapcsolva"
        )

    # --- 2. A BAL oldal hianyzik -> szarmaztatjuk (M4) ---
    if left is None and not missing_operands:
        value = _combine(list(operands.values()), rule.operation)  # type: ignore[arg-type]
        fields[rule.left] = _derived(
            fields.get(rule.left),
            value,
            f"{rule.name}: származtatva ({_operation_text(rule)}) — nem leolvasva",
        )
        return RuleOutcome(
            rule.name, "származtatva", f"{rule.left} = {_fmt(value)} ({_operation_text(rule)})"
        )

    # --- 3. EGY operandus hianyzik, a bal oldal ismert -> visszafele (M4) ---
    if left is not None and len(missing_operands) == 1:
        target = missing_operands[0]
        known = [v for k, v in operands.items() if k != target]
        value = _invert(left, known, rule.operation)  # type: ignore[arg-type]
        if value is None:
            return RuleOutcome(
                rule.name,
                "nem futott",
                f"{target} nem számolható vissza (nullával kellene osztani)",
            )
        fields[target] = _derived(
            fields.get(target),
            value,
            f"{rule.name}: visszaszámolva a(z) {rule.left!r} értékéből — nem leolvasva. "
            f"Ez a hibára kevésbé érzékeny út (M4).",
        )
        return RuleOutcome(rule.name, "származtatva", f"{target} = {_fmt(value)} (visszaszámolva)")

    return RuleOutcome(
        rule.name,
        "nem futott",
        f"túl sok hiányzó érték (bal: {'hiányzik' if left is None else 'megvan'}, "
        f"hiányzó operandusok: {missing_operands})",
    )


# ----------------------------------------------------------------------
# Számtan
# ----------------------------------------------------------------------


def _combine(values: list[float], operation: Operation) -> float:
    if operation is Operation.PRODUCT:
        return math.prod(values)
    return math.fsum(values)


def _invert(left: float, known: list[float], operation: Operation) -> Optional[float]:
    """A hiányzó operandus kiszámolása. `None`, ha nem megy."""
    if operation is Operation.PRODUCT:
        divisor = math.prod(known)
        if abs(divisor) < _NEAR_ZERO:
            # Nem adunk vegtelent vagy nullat: az CSENDES tevedes lenne.
            return None
        return left / divisor
    return left - math.fsum(known)


def _operation_text(rule: ConsistencyRule) -> str:
    jel = " × " if rule.operation is Operation.PRODUCT else " + "
    return jel.join(rule.operands)


def _fmt(value: float) -> str:
    """Napló-alak: ne írjunk ki 17 tizedesjegyet egy kerekítési hibáról."""
    return f"{value:.6g}"


# ----------------------------------------------------------------------
# Mező-frissítés
# ----------------------------------------------------------------------


def _numeric(item: Optional[Extracted[Any]]) -> Optional[float]:
    """A mező számértéke, ha van. `None`, ha hiányzik vagy nem szám.

    ⚠ A `bool` **nem** szám: a Pythonban `bool` az `int` altípusa, tehát egy
    logikai mező észrevétlenül 1-ként vagy 0-ként vennne részt a számtanban — és
    egy egyenlőség attól „stimmelne", ami nem is szám.
    """
    if item is None or item.value is None:
        return None
    if isinstance(item.value, bool):
        return None
    if isinstance(item.value, (int, float)):
        return float(item.value)
    return None


def _flag(item: Extracted[Any], note: str) -> Extracted[Any]:
    """Jelölés: a megbízhatóság legfeljebb `NEEDS_REVIEW` lesz, az érték marad.

    A `MISSING`-et **nem** rontjuk el: annak nincs értéke, és az `Extracted`
    invariánsa szerint nem is lehet. Egy már bizonytalan mező jelölése pedig ne
    írja felül a korábbi, konkrétabb indokot — **hozzáfűzzük**.
    """
    if item.confidence is Confidence.MISSING:
        return Extracted(
            value=None,
            confidence=Confidence.MISSING,
            evidence=item.evidence,
            note=_append(item.note, note),
        )
    return Extracted(
        value=item.value,
        confidence=Confidence.NEEDS_REVIEW,
        evidence=item.evidence,
        note=_append(item.note, note),
    )


def _derived(item: Optional[Extracted[Any]], value: float, note: str) -> Extracted[Any]:
    """Származtatott érték — SOHA nem `CONFIRMED`.

    Egy származtatott érték, ami megkülönböztethetetlen a leolvasottól, csendes
    tévedés: a fogyasztó azt hinné, ott volt a papíron.
    """
    return Extracted(
        value=value,
        confidence=Confidence.NEEDS_REVIEW,
        evidence=item.evidence if item is not None else None,
        note=_append(item.note if item is not None else None, note),
    )


def _append(existing: Optional[str], addition: str) -> str:
    return f"{existing} | {addition}" if existing else addition
