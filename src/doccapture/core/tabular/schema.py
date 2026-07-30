"""Oszlop-térképezés: fejléc-nevekből stabil belső kulcsok.

MIÉRT A MAGBAN VAN, ÉS NEM AZ ADAPTERBEN
----------------------------------------
Több adapter olvas táblázatot (elválasztott szöveg, munkafüzet, és lesz több).
Ha a fejléc-illesztés az adapterekben lenne, **ugyanarról a szabályról két
igazság** keletkezne — és amikor a kettő elcsúszik, az egyik csendben hazudni
fog. Az adapter dolga annyi, hogy **cellákat ad**; hogy azokból mi lesz,
domain-döntés.

A LEGFONTOSABB SZABÁLY: A KÉTÉRTELMŰSÉG HIBA, NEM VÁLASZTÁS
-----------------------------------------------------------
Ha két oszlop is illik ugyanarra a specifikációra, elbukunk. A csábító
alternatíva („vedd az elsőt") a legrosszabb lehetőség: **működni fog**, és
hónapokig nem derül ki, hogy a rossz oszlopból tölt.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from doccapture.core.errors import (
    AmbiguousHeaderError,
    ConfigurationError,
    SchemaMismatchError,
)
from doccapture.core.tabular.options import TabularOptions


class ColumnType(str, Enum):
    """Egy oszlop várt típusa.

    Nem a tárolás miatt van, hanem hogy az **értelmezés** kimondott legyen: egy
    szövegként beolvasott szám később bármikor rosszul konvertálódhat, és akkor
    a hiba messze lesz az okától.
    """

    TEXT = "text"
    NUMBER = "number"
    INTEGER = "integer"
    DATE = "date"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class ColumnSpec:
    """Egy oszlop leírása: mi a belső kulcsa, és milyen fejlécek illenek rá."""

    key: str
    """A belső, STABIL kulcs. A fogyasztó ezt látja, nem a fejléc szövegét.

    Ez a lényeg: a külső fél a saját szavaival ír, mi a saját kulcsainkkal
    dolgozunk (M5). Ha a fogyasztó a fejléc-szöveget használná, egy átnevezett
    oszlop az egész lánc mentén hibát okozna.
    """

    headers: tuple[str, ...]
    """Elfogadott fejléc-változatok. **Konfiguráció**, nem kód.

    Több változat, mert ugyanazt a mezőt minden rendszer máshogy hívja — és a
    bevezetés során ez a lista **nő**, ugyanúgy, ahogy a megfeleltetési tábla.
    """

    column_type: ColumnType = ColumnType.TEXT

    required: bool = False
    """Az OSZLOP léte kötelező-e. Ha nincs meg, a fájl e sémával nem értelmezhető.

    ⚠ Nem ugyanaz, mint hogy az érték kötelező: egy üres cella `MISSING`, azaz
    **adat**, nem kivétel. Kivételt csak a séma-szintű hiba dob.
    """

    field_type: str = ""
    """Mezőtípus-címke az M7-hez (`human_only_field_types`). `""` = nincs.

    Ha ez a címke szerepel a config emberi-kitöltés listáján, akkor ezt az
    oszlopot **nem olvassuk gépileg**, hanem kimondott hiányt adunk.
    """

    def __post_init__(self) -> None:
        if not self.key:
            raise ConfigurationError("Az oszlop belső kulcsa nem lehet üres.")
        if not self.headers:
            raise ConfigurationError(
                f"A(z) {self.key!r} oszlophoz egyetlen elfogadott fejléc sincs — "
                f"így soha nem tudna illeszkedni."
            )


@dataclass(frozen=True)
class ColumnBinding:
    """Egy specifikáció ÉS a konkrét fájl egy oszlopa közötti kötés."""

    spec: ColumnSpec
    index: int
    """0-alapú oszlop-index a beolvasott sorokban."""

    raw_header: str
    """A fejléc pontosan úgy, ahogy a fájlban áll — a bizonyítékhoz kell."""

    unit: str = ""
    """A fejlécből kinyert mértékegység (`Hossz (mm)` → `mm`). `""` = nincs.

    Megőrizzük, de NEM konvertálunk (M15). Az import-discovery terminál élő
    tapasztalata: *„mértékegységet nem szabad feltételezni"* — egy cm-ben
    vezetett lap mm-ként értelmezve tízszeresen hibás, és semmi nem jelzi.
    """


@dataclass(frozen=True)
class SchemaBinding:
    """A séma és egy konkrét fájl fejlécének illesztési eredménye.

    Szándékosan hordozza azt is, ami **nem** illeszkedett: ha nincs hova írni,
    akkor nem lesz megírva, és a betöltés hiánytalannak fog látszani.
    """

    columns: tuple[ColumnBinding, ...]

    unmatched_headers: tuple[tuple[int, str], ...] = ()
    """(index, nyers fejléc) — a fájlban van, a sémában nincs.

    Nem hiba: egy valós export tele van olyan oszloppal, ami nekünk nem kell.
    De **kimondjuk**, mert ha épp elgépelt fejléc miatt nem illeszkedett, az
    csak itt látszik.
    """

    missing_optional_keys: tuple[str, ...] = ()
    """Nem kötelező oszlopok, amik nincsenek meg a fájlban."""

    def by_key(self, key: str) -> Optional[ColumnBinding]:
        for binding in self.columns:
            if binding.spec.key == key:
                return binding
        return None

    @property
    def units(self) -> dict[str, str]:
        """Kulcs → a fejlécből kinyert mértékegység (csak ahol volt)."""
        return {b.spec.key: b.unit for b in self.columns if b.unit}


@dataclass(frozen=True)
class TableSchema:
    """Egy táblázat elvárt alakja."""

    columns: tuple[ColumnSpec, ...]

    identity_keys: tuple[str, ...] = ()
    """Azok a kulcsok, amik együtt azonosítják, hogy a sor EGYÁLTALÁN sor-e.

    Ha MINDEGYIK üres, a sort üresnek tekintjük és kihagyjuk — **de
    megszámoljuk**. A prototípus itt `if desc:`-cel némán dobott sorokat, és
    nem lehetett megtudni, hogy 0-t vagy 40-et. Üres lista = nincs ilyen
    szabály, minden sor adatsor.
    """

    def __post_init__(self) -> None:
        if not self.columns:
            raise ConfigurationError("Üres séma: egyetlen oszlopot sem ír le.")
        keys = [spec.key for spec in self.columns]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise ConfigurationError(
                f"Ugyanaz a belső kulcs több oszlopon: {duplicates}. "
                f"A fogyasztó nem tudná eldönteni, melyiket kapja."
            )
        unknown = sorted(set(self.identity_keys) - set(keys))
        if unknown:
            raise ConfigurationError(
                f"Az `identity_keys` nem létező kulcsra hivatkozik: {unknown}. "
                f"Így a sor-üresség szabálya soha nem teljesülne."
            )

    def spec_for(self, key: str) -> Optional[ColumnSpec]:
        for spec in self.columns:
            if spec.key == key:
                return spec
        return None

    # ------------------------------------------------------------------
    # Illesztés
    # ------------------------------------------------------------------

    def bind(
        self, headers: list[str], options: Optional[TabularOptions] = None
    ) -> SchemaBinding:
        """A fájl fejléc-sorát a sémához köti.

        Elbukik, ha
        - egy **kötelező** oszlop nincs meg,
        - egy specifikációra **több** oszlop illik (kétértelműség),
        - két specifikáció **ugyanarra** az oszlopra illik.

        Mindhárom eset olyan, ahol a „valamit csak válasszunk" viselkedés
        működne, és épp ezért lenne veszélyes.
        """
        options = options or TabularOptions()

        # A fejlecbol leszedjuk a mertekegyseget, es a MARADEKOT illesztjuk.
        # Igy a "Mennyiseg (m2)" es a "Mennyiseg" ugyanarra az oszlopra illik,
        # de az egyseg nem vesz el.
        parsed: list[tuple[str, str, str]] = []  # (normalizalt, nyers, egyseg)
        for raw in headers:
            label, unit = split_header_unit(raw, options.unit_bracket_pairs)
            parsed.append((normalize_header(label, options), raw, unit))

        bindings: list[ColumnBinding] = []
        missing_optional: list[str] = []
        used_indexes: dict[int, str] = {}

        for spec in self.columns:
            accepted = {normalize_header(name, options) for name in spec.headers}
            hits = [
                index
                for index, (normalized, _raw, _unit) in enumerate(parsed)
                if normalized and normalized in accepted
            ]

            if len(hits) > 1:
                raise AmbiguousHeaderError(
                    f"A(z) {spec.key!r} oszlopra több fejléc is illik: "
                    f"{[parsed[i][1] for i in hits]} (index: {hits}). "
                    f"Nem választunk közülük — a rossz oszlopból töltés hónapokig "
                    f"nem derülne ki. Pontosítsd az elfogadott fejléceket."
                )

            if not hits:
                if spec.required:
                    raise SchemaMismatchError(
                        f"Kötelező oszlop nincs meg: {spec.key!r} "
                        f"(elfogadott fejlécek: {list(spec.headers)}). "
                        f"A fájl fejléce: {headers}"
                    )
                missing_optional.append(spec.key)
                continue

            index = hits[0]
            if index in used_indexes:
                raise AmbiguousHeaderError(
                    f"Ugyanaz az oszlop ({parsed[index][1]!r}, index {index}) két "
                    f"specifikációra is illik: {used_indexes[index]!r} és "
                    f"{spec.key!r}. Egy oszlop nem lehet két különböző mező."
                )
            used_indexes[index] = spec.key
            bindings.append(
                ColumnBinding(
                    spec=spec,
                    index=index,
                    raw_header=parsed[index][1],
                    unit=parsed[index][2],
                )
            )

        unmatched = tuple(
            (index, raw)
            for index, (_normalized, raw, _unit) in enumerate(parsed)
            if index not in used_indexes and str(raw).strip()
        )

        return SchemaBinding(
            columns=tuple(bindings),
            unmatched_headers=unmatched,
            missing_optional_keys=tuple(missing_optional),
        )

    # ------------------------------------------------------------------
    # Szerializálás — a séma ADAT, nem kód
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": [
                {
                    "key": spec.key,
                    "headers": list(spec.headers),
                    "column_type": spec.column_type.value,
                    "required": spec.required,
                    "field_type": spec.field_type,
                }
                for spec in self.columns
            ],
            "identity_keys": list(self.identity_keys),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TableSchema":
        """Séma betöltése beállítás-fájlból.

        Miért kell: a mezőnevek **konfiguráció**. Ha a séma kódban állna, minden
        új ügyfél kódmódosítást igényelne — és a termék egyetlen ügyfélnél lenne
        használható.
        """
        raw_columns = data.get("columns")
        if not isinstance(raw_columns, list) or not raw_columns:
            raise ConfigurationError(
                "A séma-leírásban nincs `columns` lista, vagy üres."
            )

        specs: list[ColumnSpec] = []
        for entry in raw_columns:
            if not isinstance(entry, dict):
                raise ConfigurationError(f"Oszlop-leírás nem objektum: {entry!r}")
            type_name = entry.get("column_type", ColumnType.TEXT.value)
            try:
                column_type = ColumnType(type_name)
            except ValueError as exc:
                raise ConfigurationError(
                    f"Ismeretlen oszlop-típus: {type_name!r}. "
                    f"Választhatók: {[t.value for t in ColumnType]}"
                ) from exc
            headers = entry.get("headers", [])
            if isinstance(headers, str):
                # Gyakori elirasa a beallitas-fajlnak: egy sztring lista helyett.
                # Csendben karakterekre esne szet, ezert kimondjuk.
                raise ConfigurationError(
                    f"A(z) {entry.get('key')!r} oszlop `headers` mezője sztring, "
                    f"pedig listát vár — így karakterekre esne szét."
                )
            specs.append(
                ColumnSpec(
                    key=str(entry.get("key", "")),
                    headers=tuple(str(name) for name in headers),
                    column_type=column_type,
                    required=bool(entry.get("required", False)),
                    field_type=str(entry.get("field_type", "")),
                )
            )

        return cls(
            columns=tuple(specs),
            identity_keys=tuple(str(key) for key in data.get("identity_keys", [])),
        )


# ----------------------------------------------------------------------
# Fejléc-normalizálás
# ----------------------------------------------------------------------


def normalize_header(raw: Any, options: Optional[TabularOptions] = None) -> str:
    """Fejléc összehasonlítható alakra hozása.

    Amit MINDIG megteszünk: körülvágás és a belső szóköz-sorozatok
    összevonása. Ezek biztonságosak — nincs olyan táblázat, ahol két oszlop
    csak a szóközök számában különbözne, és a másolt fejlécekben rendszeresen
    van törhetetlen szóköz vagy soremelés.

    Amit CSAK kérésre: ékezet-hajtogatás (ld. `header_match_strip_accents`).
    """
    options = options or TabularOptions()
    text = "" if raw is None else str(raw)

    # A str.split() minden Unicode-terkozt kezel (torhetetlen szokoz, tabulator,
    # soremeles) -- ezert nem sajat karakter-listaval dolgozunk: az kimaradna
    # valamit, es a kimarado eset pont a masolt fejlecekben gyakori.
    text = " ".join(text.split())

    if options.header_match_strip_accents:
        text = _fold_accents(text)
    if options.header_match_casefold:
        text = text.casefold()
    return text


def _fold_accents(text: str) -> str:
    """Ékezet-eltávolítás kanonikus bontással."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def split_header_unit(raw: Any, bracket_pairs: Optional[list[str]] = None) -> tuple[str, str]:
    """Fejléc szétvágása címkére és mértékegységre: `Hossz (mm)` → `("Hossz", "mm")`.

    Csak a fejléc VÉGÉN álló zárójelet vesszük egységnek. Középen álló zárójel
    (`Nettó (áfa nélkül) érték`) nem egység — és ha annak vennénk, a címkét
    rontanánk el.
    """
    pairs = bracket_pairs if bracket_pairs is not None else ["()", "[]"]
    text = "" if raw is None else str(raw).strip()

    for pair in pairs:
        if len(pair) != 2:
            continue
        opening, closing = pair[0], pair[1]
        if not text.endswith(closing):
            continue
        start = text.rfind(opening)
        if start <= 0:
            # start == 0 eseten a TELJES fejlec zarojelben van -- az nem
            # "cimke + egyseg", hanem egy zarojelezett cimke. Nem bantjuk.
            continue
        unit = text[start + 1 : -1].strip()
        label = text[:start].strip()
        if not unit or not label:
            continue
        return label, unit

    return text, ""
