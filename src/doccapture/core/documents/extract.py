"""Címke → érték kinyerés szövegsorokból, determinisztikusan.

MIÉRT SORBÓL, ÉS MIÉRT NEM MINTÁBÓL
-----------------------------------
A címke-alapú kinyerés **auditálható**: megmondható, melyik sorban találtuk. Egy
szabad minta-nyelv (regex a configban) erősebb lenne, de két árat kérne: a
szabályt nem lehet szemrevételezéssel ellenőrizni, és egy rosszul megírt minta
csendben rossz értéket adna.

A KÉT ELRENDEZÉS, AMIT FED — ÉS AMIT NEM
----------------------------------------
- **egy sorban:** `Címke: érték` → az érték a címke után;
- **két sorban:** a címke sorában nincs érték → a **következő nem üres** sor.
  (Ez a hasábos elrendezés miatt kell: szkennelésnél a címke és az értéke
  gyakran külön sorba kerül.)

⚠ **Amit NEM fed:** ha a címke egy táblázat-fejléc és az érték három sorral
lejjebb van, ez nem fogja megtalálni — ott a **táblázatos út** a helyes eszköz.
Ezt kimondjuk, mert egy „nem találtam" könnyen látszik hibának, pedig itt a
rossz eszköz választása a hiba.

A KÉTÉRTELMŰSÉG ITT IS JELZÉS
-----------------------------
Ha ugyanaz a címke **több helyen, eltérő értékkel** szerepel, `NEEDS_REVIEW` megy
vele, és a diagnosztika **mindkét helyet** kiírja. Az első találat elfogadása
működne — és épp ezért lenne veszélyes.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from doccapture.core.models import Confidence, Extracted, SourceEvidence
from doccapture.core.documents.detect import normalize_text
from doccapture.core.documents.profile import DocumentProfile, FieldSpec
from doccapture.core.tabular.options import TabularOptions
from doccapture.core.tabular.values import interpret_cell

# A cimke es az ertek kozotti valasztojelek. Konfiguraciora nincs szuksege: ezek
# irasrendszer-fuggetlen irasjelek, nem locale-dontes.
_LABEL_SEPARATORS = (":", "-", "–", "—", "=", ".")


def extract_fields(
    lines: Sequence[str],
    profile: DocumentProfile,
    options: Optional[TabularOptions] = None,
    evidence: Optional[SourceEvidence] = None,
    human_only_field_types: Optional[list[str]] = None,
    line_locator: Optional[str] = None,
) -> tuple[dict[str, Extracted[Any]], list[str]]:
    """A profil mezőinek kinyerése. Visszaad: (mezők, diagnosztika).

    `line_locator`: minta a bizonyíték hely-megjelöléséhez, `{}` helyettesítővel
    a sorszámra (pl. `"1.oldal!L{}"`). Ha nincs, `L<sor>` lesz.
    """
    options = options or TabularOptions()
    human_only_field_types = human_only_field_types or []
    diagnostics: list[str] = []
    fields: dict[str, Extracted[Any]] = {}

    normalized_lines = [normalize_text(line) for line in lines]
    # ELOSZOR kiosztjuk a sorokat (a leghosszabb cimke nyer), csak UTANA olvasunk.
    # Ha mezonkent, egymastol fuggetlenul keresnenk, egy rovidebb cimke elvinne egy
    # hosszabb mezo sorat -- csendben.
    claims = claim_lines(normalized_lines, profile.fields)

    for spec in profile.fields:
        hits = _find_label_hits(lines, claims[spec.key])
        human_only = bool(spec.field_type and spec.field_type in human_only_field_types)

        if not hits:
            fields[spec.key] = Extracted(
                value=None,
                confidence=Confidence.MISSING,
                evidence=evidence,
                note=f"nem találtam címkét ({list(spec.labels)})",
            )
            if spec.required:
                # A "kotelezo" itt nem kivetelt jelent: a hiany ADAT. De KIMONDJUK,
                # kulonben egy hianyos irat teljesnek latszik.
                diagnostics.append(
                    f"kötelező mező nem található: {spec.key} (címkék: {list(spec.labels)})"
                )
            continue

        distinct = {raw for _, raw in hits}
        line_number, raw_value = hits[0]
        cell_evidence = _with_locator(evidence, line_number, line_locator)
        item = interpret_cell(raw_value, spec, options, cell_evidence, human_only=human_only)

        if len(distinct) > 1 and item.value is not None:
            # Nem az elsot fogadjuk el csendben: ket eltero ertek ugyanarra a
            # cimkere azt jelenti, hogy valamelyik biztosan rossz.
            item = Extracted(
                value=item.value,
                confidence=Confidence.NEEDS_REVIEW,
                evidence=item.evidence,
                note=_append(
                    item.note,
                    "ugyanez a címke több helyen, ELTÉRŐ értékkel szerepel: "
                    + "; ".join(f"L{n}={v!r}" for n, v in hits),
                ),
            )
            diagnostics.append(
                f"kétértelmű mező: {spec.key} — {len(distinct)} eltérő érték "
                + ", ".join(f"L{n}" for n, _ in hits)
            )

        fields[spec.key] = item

    return fields, diagnostics


def _find_label_hits(
    lines: Sequence[str], claimed: list[tuple[int, str]]
) -> list[tuple[int, str]]:
    """A kiosztott sorokból `(sorszám, nyers érték)` párok.

    A kiosztást **paraméterként** kapja, nem modul-szintű állapotból: két
    párhuzamos elemzés kiosztása különben összekeveredne, és a hiba
    **nem-determinisztikus** lenne — a legrosszabb fajta.
    """
    hits: list[tuple[int, str]] = []
    for index, label in claimed:
        value = _value_after_label(lines[index], label)
        if value:
            hits.append((index + 1, value))
        else:
            nxt = _next_non_empty(lines, index + 1)
            if nxt is not None:
                hits.append((nxt[0] + 1, nxt[1]))
    return hits


def label_matches(normalized_line: str, normalized_label: str) -> int:
    """A címke pozíciója a sorban SZÓHATÁRON, vagy `-1`.

    ⚠ **Ezt a szóhatár-vizsgálatot egy bukó teszt hozta elő, és valódi hiba
    volt.** Puszta részszöveg-kereséssel az `"Ado"` címke beleillett az
    `"Adoalap: 100000"` sorba — vagyis **a rövidebb címke elszívta a hosszabb
    mező sorát**, és a végén az adó mezőbe `"alap: 100000"` került, ami nem szám,
    tehát hiány lett belőle.

    És ami ennél is tanulságosabb: a hibát **elmaszkolta a származtatás** (M4
    kitöltötte a hiányzó adót a végösszegből, a *helyes* értékkel). A kimenet
    tehát **jónak látszott**, miközben a kinyerés rossz volt — a javító
    mechanizmus elrejtette a hibát, amit javítani hivatott.
    """
    position = normalized_line.find(normalized_label)
    while position >= 0:
        before_ok = position == 0 or not normalized_line[position - 1].isalnum()
        after = position + len(normalized_label)
        after_ok = after >= len(normalized_line) or not normalized_line[after].isalnum()
        if before_ok and after_ok:
            return position
        position = normalized_line.find(normalized_label, position + 1)
    return -1


def claim_lines(
    normalized_lines: Sequence[str], specs: Sequence[FieldSpec]
) -> dict[str, list[tuple[int, str]]]:
    """Melyik sort MELYIK mező kapja meg — a LEGHOSSZABB illeszkedő címke nyer.

    Miért kell soros előszűrés, és miért nem elég a szóhatár: két mező címkéje
    lehet egymás **szó-részhalmaza** (pl. `"Idő"` és `"Összes idő"`). A szóhatár
    ott nem segít, mert a rövidebb címke is szóhatáron áll. Ha nem döntenénk, a
    rövidebb címkéjű mező **elvinné** a hosszabb sorát — csendben.

    Holtverseny (két ugyanolyan hosszú címke ugyanabban a sorban) esetén
    **mindkettő megkapja**: az valódi kétértelműség, és a mező-szintű
    kétértelműség-jelzés fogja megmutatni.
    """
    claims: dict[str, list[tuple[int, str]]] = {spec.key: [] for spec in specs}

    for index, normalized in enumerate(normalized_lines):
        best_length = 0
        winners: list[tuple[str, str]] = []
        for spec in specs:
            for label in spec.labels:
                needle = normalize_text(label)
                if not needle or label_matches(normalized, needle) < 0:
                    continue
                if len(needle) > best_length:
                    best_length, winners = len(needle), [(spec.key, label)]
                elif len(needle) == best_length:
                    winners.append((spec.key, label))
                break  # egy specen belul az elso illeszkedo valtozat eleg
        for key, label in winners:
            claims[key].append((index, label))

    return claims


def _value_after_label(line: str, label: str) -> str:
    """A címke UTÁNI rész ugyanabban a sorban, választójelek nélkül.

    A keresés a normalizált alakon történik, de a **kivágás a nyers soron** — így
    az érték eredeti alakja (ékezetek, kis-nagybetű) megmarad. Ha a normalizálás
    hosszt változtatna, a kivágás elcsúszna; ezért a hosszt ellenőrizzük, és
    eltérésnél inkább **nem vágunk**, mint hogy rossz helyen vágjunk.
    """
    normalized_line = normalize_text(line)
    needle = normalize_text(label)
    position = normalized_line.find(needle)
    if position < 0:
        return ""

    if len(normalized_line) != len(line.strip()):
        # Az osszevont szokozok / hajtogatott ekezetek eltoltak a poziciokat.
        # Ilyenkor a NYERS soron keresunk kis-nagybetu-fuggetlenul; ha az sem megy,
        # nem talalgatunk.
        lowered = line.casefold()
        position = lowered.find(label.casefold())
        if position < 0:
            return ""
        tail = line[position + len(label) :]
    else:
        tail = line.strip()[position + len(needle) :]

    return tail.strip().lstrip("".join(_LABEL_SEPARATORS)).strip()


def _next_non_empty(lines: Sequence[str], start: int) -> Optional[tuple[int, str]]:
    for index in range(start, len(lines)):
        if lines[index].strip():
            return index, lines[index].strip()
    return None


def _with_locator(
    evidence: Optional[SourceEvidence], line_number: int, pattern: Optional[str]
) -> Optional[SourceEvidence]:
    if evidence is None:
        return None
    locator = pattern.format(line_number) if pattern else f"L{line_number}"
    return SourceEvidence(
        relative_path=evidence.relative_path,
        content_hash=evidence.content_hash,
        locator=locator,
    )


def _append(existing: Optional[str], addition: str) -> str:
    return f"{existing} | {addition}" if existing else addition
