"""Irat-profil: mi az irat, és mit kérünk tőle.

MIÉRT KÜLÖN TENGELY AZ `InputKind`-TÓL
-------------------------------------
Az `InputKind` azt mondja meg, **hogyan olvassuk** (táblázat · szövegréteg ·
raszter · kézírás). A profil azt, hogy **mi az irat, és mit kell kinyerni belőle**.

A kettő **szorzat, nem összeg**: egy munkalap jöhet szkennelve *és* táblázatként,
egy számla lehet digitális *és* papír. Ha egy tengelyre húznánk őket
(`SZKENNELT_MUNKALAP`, `DIGITALIS_SZAMLA`, …), az esetek összeszorzódnának, és
minden új irat-típus **négy** új ágat jelentene.

A PROFIL ADAT, NEM KÓD — ÉS EZ A SEMLEGESSÉG FELTÉTELE
------------------------------------------------------
Egy iparág-agnosztikus motorba nem kerülhet be konkrét iparág mezőkészlete. Ezért
a motor a **mechanizmust** adja, a profilokat a fogyasztó — `from_dict()`-en át,
ugyanúgy, ahogy a `TableSchema`-t. A bevezetés során a profil **nő**, ahogy a
megfeleltetési tábla is (M5).

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from doccapture.core.errors import ConfigurationError
from doccapture.core.tabular.schema import ColumnType


@dataclass(frozen=True)
class FieldSpec:
    """Egy kinyerendő mező: milyen címkék vezetik be, és mi a típusa."""

    key: str
    """A belső, STABIL kulcs — a fogyasztó ezt látja, nem a címke szövegét."""

    labels: tuple[str, ...]
    """Elfogadott címke-változatok. **Konfiguráció**, és a bevezetés során nő.

    Miért több: ugyanazt a mezőt minden kibocsátó máshogy nevezi. A lista bővítése
    **nem** kódmódosítás.
    """

    value_type: ColumnType = ColumnType.TEXT
    """Az érték típusa — **ugyanaz az enum**, amit a táblázatos út használ.

    Szándékosan nem külön típus-készlet: ha kettő lenne, az érték-értelmezésről
    két igazság keletkezne, és az egyik előbb-utóbb elcsúszna.
    """

    required: bool = False
    """A MEZŐ kötelező-e. ⚠ Nem ugyanaz, mint hogy az érték kötelező: egy meg nem
    talált mező `MISSING`, azaz **adat**. A `required` csak azt jelenti, hogy a
    hiánya **kimondott diagnosztikát** ér, nem csendes átlépést."""

    field_type: str = ""
    """Mezőtípus-címke az M7-hez (`human_only_field_types`). `""` = nincs."""

    # A `values.interpret_cell` csak a `column_type` es a `field_type` mezot
    # hasznalja. Ez az alias teszi lehetove, hogy a FieldSpec ugyanazt az
    # ertelmezot hasznalja, mint a tablazatos oszlop -- EGY igazsag ket uton.
    @property
    def column_type(self) -> ColumnType:
        return self.value_type

    def __post_init__(self) -> None:
        if not self.key:
            raise ConfigurationError("A mező belső kulcsa nem lehet üres.")
        if not self.labels:
            raise ConfigurationError(
                f"A(z) {self.key!r} mezőhöz egyetlen címke sincs — így soha nem "
                f"lehetne megtalálni."
            )


class Operation(str, Enum):
    """Az önellenőrző számtan megengedett műveletei.

    Szándékosan **zárt készlet**, nem kifejezés-nyelv: egy szabad kifejezés
    kiértékeléséhez `eval` kellene, ami egy publikus termékben olyan minta, amit
    nem vállalunk — és auditálhatatlan is. Ez a két művelet lefedi az üzleti
    iratok redundanciáját (tétel-érték, adóalap+adó, idő-összegek).
    """

    PRODUCT = "product"
    """`bal = operandusok szorzata` — pl. tétel-érték = mennyiség × egységár."""

    SUM = "sum"
    """`bal = operandusok összege` — pl. végösszeg = adóalap + adó."""


@dataclass(frozen=True)
class ConsistencyRule:
    """Egy önellenőrző egyenlőség az iraton (M3), származtatással (M4).

    **M3 — a redundancia ingyen ellenőrzés.** Az üzleti iratok tele vannak
    önellenőrző számtannal. Ha nem stimmel (tűréssel), **jelöljük, nem javítjuk
    csendben** — és a diagnosztika **megnevezi, MELYIK egyenlőség bomlott el**,
    mert a hiba abból visszafejthető.

    **M4 — a hibára legkevésbé érzékeny bemenet.** Ha egy érték hiányzik, de a
    többiből kiszámolható, a szabály **kitöltheti** — `NEEDS_REVIEW`
    megbízhatósággal, és a származtatás útja kimondva.
    """

    name: str
    """Ember számára olvasható név. Ez jelenik meg a diagnosztikában, ezért
    mondja meg, MELYIK egyenlőségről van szó."""

    left: str
    """A bal oldal mező-kulcsa."""

    operands: tuple[str, ...]
    """A jobb oldal mező-kulcsai."""

    operation: Operation = Operation.PRODUCT

    tolerance: Optional[float] = None
    """Megengedett eltérés. `None` = a config `redundancy_tolerance` értéke.

    Miért lehet szabály-szintű: egy pénz-egyenlőség tűrése (kerekítés) más, mint
    egy idő-összegé. Egy globális tűrés vagy túl szoros, vagy túl megengedő.
    """

    derive: bool = True
    """Kitöltheti-e a szabály a hiányzó értéket (M4)."""

    def __post_init__(self) -> None:
        if not self.name:
            raise ConfigurationError("A szabálynak neve kell — a diagnosztika azt írja ki.")
        if not self.left:
            raise ConfigurationError(f"A(z) {self.name!r} szabálynak nincs bal oldala.")
        if len(self.operands) < 2:
            raise ConfigurationError(
                f"A(z) {self.name!r} szabály legalább két operandust vár — "
                f"egyetlen operandussal nincs mit ellenőrizni."
            )
        if self.left in self.operands:
            raise ConfigurationError(
                f"A(z) {self.name!r} szabály bal oldala a jobb oldalon is szerepel "
                f"({self.left!r}) — az egyenlőség önmagát ellenőrizné."
            )
        if self.tolerance is not None and self.tolerance < 0:
            raise ConfigurationError(f"A(z) {self.name!r} szabály tűrése negatív.")


@dataclass(frozen=True)
class DocumentProfile:
    """Egy irat-típus: horgonyok, mezők, önellenőrző szabályok."""

    profile_id: str
    """Stabil azonosító (pl. `"ketoldalu-kereskedelmi-irat"`). A fogyasztó ezt látja."""

    required_anchors: tuple[str, ...] = ()
    """Horgonyok, amiknek MINDEGYIKÉNEK szerepelnie kell.

    **M1 — horgony-fél és ellenfél.** A felismerés **stabil azonosítóval**
    történik (adószám, regisztrációs szám — konfigurációból), nem névvel: a név
    elírható, az azonosító nem.
    """

    optional_anchors: tuple[str, ...] = ()
    """További jelek. Nem kötelezőek, de **pontot adnak** — így két illeszkedő
    profil között a több bizonyítékkal rendelkező nyer."""

    fields: tuple[FieldSpec, ...] = ()
    rules: tuple[ConsistencyRule, ...] = ()

    description: str = ""
    """Mire való ez a profil — ember számára. A diagnosztikába is bekerül."""

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ConfigurationError("A profil azonosítója nem lehet üres.")
        if not self.required_anchors and not self.optional_anchors:
            raise ConfigurationError(
                f"A(z) {self.profile_id!r} profilnak egyetlen horgonya sincs — így "
                f"MINDEN iratra illeszkedne, és a felismerés értelmét vesztené."
            )
        keys = [f.key for f in self.fields]
        duplicates = sorted({k for k in keys if keys.count(k) > 1})
        if duplicates:
            raise ConfigurationError(
                f"A(z) {self.profile_id!r} profilban ismétlődő mező-kulcs: {duplicates}"
            )
        known = set(keys)
        for rule in self.rules:
            unknown = sorted(({rule.left} | set(rule.operands)) - known)
            if unknown:
                raise ConfigurationError(
                    f"A(z) {self.profile_id!r} profil {rule.name!r} szabálya nem "
                    f"létező mezőre hivatkozik: {unknown}. Így a szabály soha nem "
                    f"futna le, és az irat 'ellenőrzöttnek' látszana."
                )

    def field_for(self, key: str) -> Optional[FieldSpec]:
        for spec in self.fields:
            if spec.key == key:
                return spec
        return None

    @property
    def anchors(self) -> tuple[str, ...]:
        return (*self.required_anchors, *self.optional_anchors)

    # ------------------------------------------------------------------
    # Szerializálás — a profil ADAT
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "description": self.description,
            "required_anchors": list(self.required_anchors),
            "optional_anchors": list(self.optional_anchors),
            "fields": [
                {
                    "key": f.key,
                    "labels": list(f.labels),
                    "value_type": f.value_type.value,
                    "required": f.required,
                    "field_type": f.field_type,
                }
                for f in self.fields
            ],
            "rules": [
                {
                    "name": r.name,
                    "left": r.left,
                    "operands": list(r.operands),
                    "operation": r.operation.value,
                    "tolerance": r.tolerance,
                    "derive": r.derive,
                }
                for r in self.rules
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentProfile":
        """Profil betöltése leírásból. **Ez a fő út** — a profil konfiguráció."""
        fields: list[FieldSpec] = []
        for entry in data.get("fields", []):
            if not isinstance(entry, dict):
                raise ConfigurationError(f"Mező-leírás nem objektum: {entry!r}")
            labels = entry.get("labels", [])
            if isinstance(labels, str):
                # Gyakori elirasa a beallitas-fajlnak. Csendben karakterekre esne
                # szet, es a mezo soha nem illeszkedne.
                raise ConfigurationError(
                    f"A(z) {entry.get('key')!r} mező `labels` mezője sztring, pedig "
                    f"listát vár — így karakterekre esne szét."
                )
            fields.append(
                FieldSpec(
                    key=str(entry.get("key", "")),
                    labels=tuple(str(x) for x in labels),
                    value_type=_column_type(entry.get("value_type", ColumnType.TEXT.value)),
                    required=bool(entry.get("required", False)),
                    field_type=str(entry.get("field_type", "")),
                )
            )

        rules: list[ConsistencyRule] = []
        for entry in data.get("rules", []):
            if not isinstance(entry, dict):
                raise ConfigurationError(f"Szabály-leírás nem objektum: {entry!r}")
            raw_op = entry.get("operation", Operation.PRODUCT.value)
            try:
                operation = Operation(raw_op)
            except ValueError as exc:
                raise ConfigurationError(
                    f"Ismeretlen művelet: {raw_op!r}. Választhatók: "
                    f"{[o.value for o in Operation]}"
                ) from exc
            tolerance = entry.get("tolerance")
            rules.append(
                ConsistencyRule(
                    name=str(entry.get("name", "")),
                    left=str(entry.get("left", "")),
                    operands=tuple(str(x) for x in entry.get("operands", [])),
                    operation=operation,
                    tolerance=None if tolerance is None else float(tolerance),
                    derive=bool(entry.get("derive", True)),
                )
            )

        return cls(
            profile_id=str(data.get("profile_id", "")),
            description=str(data.get("description", "")),
            required_anchors=tuple(str(x) for x in data.get("required_anchors", [])),
            optional_anchors=tuple(str(x) for x in data.get("optional_anchors", [])),
            fields=tuple(fields),
            rules=tuple(rules),
        )


def _column_type(name: Any) -> ColumnType:
    try:
        return ColumnType(name)
    except ValueError as exc:
        raise ConfigurationError(
            f"Ismeretlen érték-típus: {name!r}. Választhatók: "
            f"{[t.value for t in ColumnType]}"
        ) from exc
