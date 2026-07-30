"""Nyers rács → `TabularReadResult`. A KÖZÖS igazság mindkét adapter alatt.

MIÉRT VAN EGYÁLTALÁN ILYEN MODUL
--------------------------------
Két adapter olvas ma táblázatot (elválasztott szöveg, munkafüzet), és lesz több.
Ha mindegyik maga állítaná össze az eredményt, akkor **ugyanarról a szabályról
két igazság** lenne — a sor-üresség, a mértékegység megőrzése, a kihagyás
számolása és a korlát-jelzés mind kétszer volna leírva. A platformon ma ez a
leggyakoribb hibánk: amikor ugyanazt két helyen számoljuk, az egyik előbb-utóbb
hazudni fog.

Az adapter dolga ezért **annyi**, hogy fejlécet és cella-sorokat ad. Minden
egyéb itt történik, egy helyen, infrastruktúra nélkül — tehát tesztelhetően.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from doccapture.core.models import Extracted, SourceEvidence
from doccapture.core.tabular.options import TabularOptions
from doccapture.core.tabular.result import TabularReadResult
from doccapture.core.tabular.schema import SchemaBinding, TableSchema
from doccapture.core.tabular.values import interpret_cell, is_blank_cell

LocatorFactory = Callable[[int, int], str]
"""(sor-szám, oszlop-index) → hely-megjelölés a bizonyítékban.

Az adapter adja, mert csak ő tudja, hogy `Munka1!B7` vagy `R7C2` az értelmes
megjelölés. A magban ezt nem lehet kitalálni — és ha kitalálnánk, az egy
konkrét fájlformátum feltevése lenne a domainben.
"""


def build_result(
    *,
    header_cells: list[Any],
    data_rows: Iterable[tuple[int, list[Any]]],
    schema: TableSchema,
    options: Optional[TabularOptions] = None,
    file_evidence: Optional[SourceEvidence] = None,
    locator_for: Optional[LocatorFactory] = None,
    header_locator: str = "",
    human_only_field_types: Optional[list[str]] = None,
    evidence_with_locator: Optional[Callable[[SourceEvidence, str], SourceEvidence]] = None,
    extra_diagnostics: Optional[list[str]] = None,
) -> TabularReadResult:
    """Fejléc + adatsorok → kész eredmény, diagnosztikával.

    `data_rows`: `(fájl-szerinti sorszám, cellák)` párok. A sorszám azért jön az
    adapterből, mert a bizonyítéknak **a fájlban lévő** helyre kell mutatnia, nem
    a mi számlálónkra — egy kihagyott fejléc-sor után a kettő elcsúszik, és a
    bizonyíték rossz helyre mutat.

    `human_only_field_types`: az M7 lista a configból. Az itt szereplő
    mezőtípusú oszlopokat **nem olvassuk gépileg**.
    """
    options = options or TabularOptions()
    human_only_field_types = human_only_field_types or []

    binding = schema.bind([_as_header_text(cell) for cell in header_cells], options)
    # Az ADAPTER eszrevetelei elore: azok a fajl egeszere allnak (pl. milyen
    # elvalasztot valasztottunk, futtatas-keres), tehat elobb kell latni oket,
    # mint a cella-szintu megjegyzeseket.
    diagnostics: list[str] = [*(extra_diagnostics or []), *_binding_diagnostics(binding)]

    rows: list[dict[str, Extracted[Any]]] = []
    skipped_blank = 0
    truncated = False

    for row_number, cells in data_rows:
        if options.max_rows and len(rows) >= options.max_rows:
            # NEM csendben allunk meg: a csonkolas ugyanugy nez ki, mint egy
            # hianytalan betoltes, ha nem mondjuk ki.
            truncated = True
            diagnostics.append(
                f"a sor-korlát ({options.max_rows}) elérve — a fájl NEM lett "
                f"végigolvasva, az első kihagyott sor: {row_number}"
            )
            break

        # Az uresseget a NYERS cellakbol dontjuk el, NEM az ertelmezett
        # ertekbol. Ld. `_is_blank_row` -- ez a sorrend egy bukó teszt
        # kovetkezmenye, es a hiba nema sor-eltunes volt.
        if _is_blank_row(cells, binding, schema):
            skipped_blank += 1
            continue

        rows.append(
            _build_row(
                cells=cells,
                row_number=row_number,
                binding=binding,
                options=options,
                file_evidence=file_evidence,
                locator_for=locator_for,
                human_only_field_types=human_only_field_types,
                evidence_with_locator=evidence_with_locator,
            )
        )

    if skipped_blank:
        diagnostics.append(
            f"{skipped_blank} sor üresként kihagyva (az azonosító oszlopok "
            f"{list(schema.identity_keys)} mindegyike üres volt)"
        )

    return TabularReadResult(
        rows=rows,
        units=binding.units,
        diagnostics=diagnostics,
        header_evidence_locator=header_locator,
        skipped_blank_rows=skipped_blank,
        unmatched_headers=binding.unmatched_headers,
        missing_optional_keys=binding.missing_optional_keys,
        truncated=truncated,
    )


def _as_header_text(cell: Any) -> str:
    return "" if cell is None else str(cell)


def _binding_diagnostics(binding: SchemaBinding) -> list[str]:
    """Amit az illesztés észrevett. Nem hiba, de nem is hallgatható el."""
    notes: list[str] = []
    if binding.unmatched_headers:
        notes.append(
            "a sémában nem szereplő fejlécek: "
            + ", ".join(f"[{index}] {raw!r}" for index, raw in binding.unmatched_headers)
            + " — ha ezek közül valamelyik elgépelt, CSAK itt látszik"
        )
    if binding.missing_optional_keys:
        notes.append(
            "nem kötelező oszlopok, amik ebben a fájlban nincsenek meg: "
            + ", ".join(binding.missing_optional_keys)
        )
    for column in binding.columns:
        if column.unit:
            notes.append(
                f"mértékegység a fejlécből: {column.spec.key} = {column.unit!r} "
                f"(megőrizve, NEM átváltva)"
            )
    return notes


def _build_row(
    *,
    cells: list[Any],
    row_number: int,
    binding: SchemaBinding,
    options: TabularOptions,
    file_evidence: Optional[SourceEvidence],
    locator_for: Optional[LocatorFactory],
    human_only_field_types: list[str],
    evidence_with_locator: Optional[Callable[[SourceEvidence, str], SourceEvidence]],
) -> dict[str, Extracted[Any]]:
    row: dict[str, Extracted[Any]] = {}
    for column in binding.columns:
        raw = cells[column.index] if column.index < len(cells) else None

        evidence = file_evidence
        if file_evidence is not None and locator_for is not None:
            locator = locator_for(row_number, column.index)
            evidence = (
                evidence_with_locator(file_evidence, locator)
                if evidence_with_locator is not None
                else SourceEvidence(
                    relative_path=file_evidence.relative_path,
                    content_hash=file_evidence.content_hash,
                    locator=locator,
                )
            )

        human_only = bool(
            column.spec.field_type and column.spec.field_type in human_only_field_types
        )
        row[column.spec.key] = interpret_cell(
            raw,
            column.spec,
            options,
            evidence,
            human_only=human_only,
        )
    return row


def _is_blank_row(
    cells: list[Any], binding: SchemaBinding, schema: TableSchema
) -> bool:
    """Üres-e a sor az azonosító oszlopok NYERS cellái szerint.

    ⚠ **A „nyers" szó itt egy megtalált hiba nyoma.** Az első változat az
    értelmezett érték megbízhatóságából döntött (`MISSING` → üres), és attól
    két eset **csendben kiütötte az egész sort**:

    1. **gyorsítótár nélküli képlet** az azonosító oszlopban — ott VAN tartalom,
       csak nem tudtuk elolvasni; a sor eltűnése helyett hiányt kell jelezni;
    2. **emberi kitöltésre jelölt** azonosító oszlop (M7) — ott szándékosan nem
       olvasunk, de a sor létezik.

    Mindkettőnél a hiány *adat*; a sor eltűnése *adatvesztés*. Az üresség tehát
    a **bemenet** tulajdonsága, nem az értelmezés eredménye — és ez a
    különbségtétel az egyetlen ok, amiért ez a függvény a nyers cellákat kapja.

    Ha nincsenek azonosító oszlopok, akkor **minden sor adatsor** — nem találjuk
    ki, mi az „üres". A prototípus itt egyetlen oszlopra (`if desc:`) döntött,
    ami egy konkrét fájl alakja volt, nem szabály.
    """
    if not schema.identity_keys:
        return False

    for key in schema.identity_keys:
        column = binding.by_key(key)
        if column is None:
            # A kulcs nem kotelezo oszlopra mutat, ami ebbol a fajlbol hianyzik.
            # Nem szol a sor uressegerol semmit -- de a tobbi kulcs meg dönthet.
            continue
        raw = cells[column.index] if column.index < len(cells) else None
        if not is_blank_cell(raw):
            return False
    return True
