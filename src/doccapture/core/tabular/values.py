"""Cella → `Extracted`: az értelmezés, ahol a bizonytalanság ADAT lesz.

A KÉT SZABÁLY, AMI MINDEN DÖNTÉST ELDÖNT ITT
--------------------------------------------
1. **„Inkább hiány, mint téves."** Ha egy érték kétértelmű, `MISSING` megy vele
   indokkal — nem a valószínűbb olvasat. A csendes tévedés drágább, mert nem
   nézi meg senki.

2. **A táblázatos forrás NEM automatikusan megbízható.** Csábító feltevés, hogy
   ami digitális, az pontos. A táblázatkezelő viszont **tudományos alakra hozza**
   a hosszú azonosítókat (16 jegyű vonalkód → `1.23457E+15`), és az eredeti
   számjegyek **véglegesen elvesznek**. Ilyenkor nem az olvasás bizonytalan,
   hanem **a forrás** már romlott — és ezt ki kell mondani.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Optional

from doccapture.core.models import Confidence, Extracted, SourceEvidence
from doccapture.core.tabular.options import TabularOptions
from doccapture.core.tabular.schema import ColumnSpec, ColumnType


@dataclass(frozen=True)
class UnreadableCell:
    """A cellában VAN valami, de az adapter nem tudta elolvasni.

    ⚠ **Ez NEM ugyanaz, mint az üres cella** — és pontosan ez a különbség a
    szelet legdrágább leletje. Ha az adapter ilyenkor `None`-t adna, az
    megkülönböztethetetlen lenne az üres cellától, és a sor akár üresnek is
    látszhatna: **néma adatvesztés**.

    Általános mechanizmus, nem egy fájlformátum részlete: bármelyik adapter
    jelezheti így, hogy „itt tartalom van, de az okot is elmondom". A mag ebből
    kimondott hiányt csinál, az indokkal együtt — a bizonytalanság így ADAT lesz,
    nem eltűnt információ.
    """

    reason: str
    """Ember számára olvasható ok. Ez kerül az `Extracted.note`-ba."""


# 2**53: e folott a lebegopontos abrazolas mar nem tud minden egeszet pontosan
# tarolni. Nem "kb. nagy szam", hanem az abrazolas kemeny hatara -- ezert
# szamitott konstans, nem beirt szam.
_EXACT_INTEGER_LIMIT = float(2**53)


def interpret_cell(
    raw: Any,
    spec: ColumnSpec,
    options: Optional[TabularOptions] = None,
    evidence: Optional[SourceEvidence] = None,
    *,
    human_only: bool = False,
) -> Extracted[Any]:
    """Egy cella nyers értékéből `Extracted` — megbízhatósággal és indokkal.

    `human_only`: az M7 kapcsolója. Ha igaz, **nem olvasunk**, hanem kimondott
    hiányt adunk. A hívó dönti el (a config `human_only_field_types` listájából),
    mert ez telepítésenként más.
    """
    options = options or TabularOptions()

    if human_only:
        # Miert dobjuk el a cella tartalmat is: ez a lista pont azokra a
        # mezotipusokra keszult, ahol a gepi olvasas tudottan megbizhatatlan.
        # Egy tablazatban ez elsore ertelmetlennek tunik -- de epp itt rontja el
        # a tablazatkezelo a hosszu azonositokat (ld. a modul fejleceben).
        return Extracted(
            value=None,
            confidence=Confidence.MISSING,
            evidence=evidence,
            note=(
                f"emberi kitöltésre jelölve (mezőtípus: {spec.field_type!r}) — "
                f"gépi olvasás kikapcsolva"
            ),
        )

    if isinstance(raw, UnreadableCell):
        # ELOBB, mint az ures-vizsgalat: itt VAN tartalom, csak nem olvashato.
        # Ha ez ures cellanak minosulne, a sor akar ures sorkent kiesne.
        return Extracted(
            value=None,
            confidence=Confidence.MISSING,
            evidence=evidence,
            note=raw.reason,
        )

    if is_blank_cell(raw):
        return Extracted(
            value=None,
            confidence=Confidence.MISSING,
            evidence=evidence,
            note="üres cella",
        )

    if spec.column_type is ColumnType.TEXT:
        return _interpret_text(raw, evidence)
    if spec.column_type in (ColumnType.NUMBER, ColumnType.INTEGER):
        return _interpret_number(raw, spec, options, evidence)
    if spec.column_type is ColumnType.DATE:
        return _interpret_date(raw, options, evidence)
    if spec.column_type is ColumnType.BOOLEAN:
        return _interpret_boolean(raw, options, evidence)

    # Ide csak akkor jutunk, ha uj ColumnType-ot vettunk fel es elfelejtettuk
    # kezelni. Nem csendben szoveggé alakitunk: az elnyelne a hibat.
    return Extracted(
        value=None,
        confidence=Confidence.MISSING,
        evidence=evidence,
        note=f"nincs értelmező a(z) {spec.column_type!r} oszlop-típushoz",
    )


def is_blank_cell(raw: Any) -> bool:
    """Üres-e a cella. A NYERS bemenetre kérdez, nem az értelmezés eredményére.

    Három dolog, ami NEM üres, és mindhárom miatt van itt külön függvény:

    - **`0` és `False`** — érvényes értékek. Egy `if not value:` mindkettőt
      üresnek vennné, és az adatvesztés.
    - **`UnreadableCell`** — itt VAN tartalom, csak nem olvasható. Ez a
      legfontosabb: ha üresnek számítana, a sor **üres sorként kiesne**, és a
      hiány helyett *semmi* maradna.

    ⚠ **Ezt a különbségtételt egy bukó saját teszt hozta elő.** A sor-üresség
    eredetileg az értelmezett érték megbízhatóságából dolgozott (`MISSING` →
    üres), és attól egy gyorsítótár nélküli képlet az azonosító oszlopban
    **csendben kiütötte az egész sort**. A jelző-érték az *indokot* megjavította,
    a sor-szintű döntést nem — a hiba fogalmi volt: az üresség a **bemenet**
    tulajdonsága, nem az értelmezés eredménye.
    """
    if isinstance(raw, UnreadableCell):
        return False
    if raw is None:
        return True
    if isinstance(raw, str) and not raw.strip():
        return True
    return False



# ----------------------------------------------------------------------
# Szöveg
# ----------------------------------------------------------------------


def _interpret_text(raw: Any, evidence: Optional[SourceEvidence]) -> Extracted[str]:
    """Szöveges oszlop — a `str()` itt NEM ártalmatlan.

    Ha a nyers érték lebegőpontos, a táblázatkezelő már átalakította a
    tartalmat. Két külön eset, két külön válasz:

    - **tudományos alak** (`1.23457e+15`): a számjegyek elvesztek → `NEEDS_REVIEW`,
      mert a helyes érték már nincs a fájlban, csak az ember tudja pótolni;
    - **tört rész nélküli lebegőpontos** (`123.0`): a `str()` `"123.0"`-t adna,
      ami egy cikkszámnál rossz kulcs → egészre hozzuk, és jelezzük.
    """
    if isinstance(raw, bool):
        # A bool a Pythonban int -- ha ide esik, elobb kell elkapni, mint a szamot.
        return Extracted(str(raw), Confidence.CONFIRMED, evidence)

    if isinstance(raw, float):
        text = repr(raw)
        if "e" in text or "E" in text:
            return Extracted(
                value=text,
                confidence=Confidence.NEEDS_REVIEW,
                evidence=evidence,
                note=(
                    "a táblázat tudományos alakra hozta az értéket — az eredeti "
                    "számjegyek elveszhettek, a forrásból kell pótolni"
                ),
            )
        if raw.is_integer() and abs(raw) >= _EXACT_INTEGER_LIMIT:
            # ⚠ EZT A SORT EGY BUKO SAJAT TESZT HOZTA ELO, es a lelet a
            # DETEKTORROL szolt, nem a kodrol: a `repr` CSAK 1e16 folott valt
            # tudomanyos alakra, a lebegopontos szam viszont mar 2**53 (kb.
            # 9,007e15) folott nem tud minden egeszet pontosan tarolni. Vagyis van
            # egy RES: 2**53 es 1e16 kozott a szamjegyek MAR elvesztek, de az
            # "e"-vizsgalat meg nem fog. Az `e`-re szurve a legveszelyesebb sav
            # csendben atment volna.
            return Extracted(
                value=str(int(raw)),
                confidence=Confidence.NEEDS_REVIEW,
                evidence=evidence,
                note=(
                    f"az érték {_EXACT_INTEGER_LIMIT:.0f} fölötti egész lebegőpontos "
                    f"alakban — ilyen nagyságtól a tárolás már nem pontos, tehát az "
                    f"utolsó számjegyek elveszhettek. Hosszú azonosítót a forrásból "
                    f"kell pótolni."
                ),
            )
        if raw.is_integer():
            return Extracted(
                value=str(int(raw)),
                confidence=Confidence.NEEDS_REVIEW,
                evidence=evidence,
                note=(
                    "szöveges oszlopban szám állt; tört rész nélkül egészként "
                    "vettük — ha azonosító, ellenőrizd a vezető nullákat"
                ),
            )

    return Extracted(str(raw).strip(), Confidence.CONFIRMED, evidence)


# ----------------------------------------------------------------------
# Szám
# ----------------------------------------------------------------------


def parse_number(
    text: str, options: Optional[TabularOptions] = None
) -> tuple[Optional[float], str]:
    """Szöveg → szám, locale nélkül. Visszatér: `(érték, indok)`.

    A SZABÁLY, ÉS MIÉRT ÉPP EZ
    --------------------------
    - **Mindkét jel szerepel** (`.` és `,`): az **utolsó** a tizedesjel, a másik
      csoport-jel. Ez univerzális — nincs olyan írásrendszer, ahol a
      csoport-jel a tizedesjel után állna.
    - **Csak az egyik, többször**: csoport-jel (`1.234.567`).
    - **Csak az egyik, egyszer, pontosan 3 számjegy követi, és az egész rész
      1-3 számjegy**: **KÉTÉRTELMŰ** (`1,234` = 1234 vagy 1.234?) → hiány.
      Ha a config megnevezi a tizedesjelet, ez az eset eltűnik.
    - **Minden más**: tizedesjel (`12,5`; `1234.56` — az utóbbinál a 4 jegyű
      egész rész kizárja az érvényes csoportosítást).
    """
    options = options or TabularOptions()
    cleaned = text.strip()
    if not cleaned:
        return None, "üres érték"

    negative = False
    if cleaned[0] in "+-":
        negative = cleaned[0] == "-"
        cleaned = cleaned[1:].strip()

    for separator in options.group_separators:
        if separator:
            cleaned = cleaned.replace(separator, "")

    if not cleaned:
        return None, "csak előjel, számjegy nélkül"

    dot_count = cleaned.count(".")
    comma_count = cleaned.count(",")
    decimal_char = ""

    if dot_count and comma_count:
        decimal_char = "." if cleaned.rfind(".") > cleaned.rfind(",") else ","
        other = "," if decimal_char == "." else "."
        cleaned = cleaned.replace(other, "")
    elif dot_count or comma_count:
        present = "." if dot_count else ","
        count = dot_count or comma_count
        configured = options.decimal_separator

        if configured == present:
            decimal_char = present
        elif configured:
            # A config mas jelet nevezett meg tizedesjelnek -> ez csoport-jel.
            cleaned = cleaned.replace(present, "")
        elif count > 1:
            cleaned = cleaned.replace(present, "")
        else:
            head, _, tail = cleaned.partition(present)
            if len(tail) == 3 and 1 <= len(head) <= 3 and head.isdigit() and tail.isdigit():
                return None, (
                    f"kétértelmű szám: {text.strip()!r} — a(z) {present!r} lehet "
                    f"tizedesjel és ezres-csoportosító is. Nem tippelünk; adj meg "
                    f"tizedesjelet a beállításban (`decimal_separator`)."
                )
            decimal_char = present

    if decimal_char and decimal_char != ".":
        cleaned = cleaned.replace(decimal_char, ".")

    try:
        value = float(cleaned)
    except ValueError:
        return None, f"nem szám alakú: {text.strip()!r}"

    return (-value if negative else value), ""


def _interpret_number(
    raw: Any,
    spec: ColumnSpec,
    options: TabularOptions,
    evidence: Optional[SourceEvidence],
) -> Extracted[Any]:
    if isinstance(raw, bool):
        # A bool int-kent szamna, es a `True` 1-re valtozna -- az csendes tevedes.
        return Extracted(
            value=None,
            confidence=Confidence.MISSING,
            evidence=evidence,
            note="logikai érték szám-oszlopban",
        )

    if isinstance(raw, (int, float)):
        value: Any = float(raw)
        problem = ""
    else:
        value, problem = parse_number(str(raw), options)

    if problem or value is None:
        return Extracted(
            value=None,
            confidence=Confidence.MISSING,
            evidence=evidence,
            note=problem or "nem értelmezhető szám",
        )

    if spec.column_type is ColumnType.INTEGER:
        if float(value).is_integer():
            return Extracted(int(value), Confidence.CONFIRMED, evidence)
        # Nem hazudunk kerekitessel, es nem is dobjuk el: az erteket megtartjuk,
        # de JELOLJUK. A fogyaszto igy latja, hogy dontenie kell.
        return Extracted(
            value=float(value),
            confidence=Confidence.NEEDS_REVIEW,
            evidence=evidence,
            note=(
                "egész oszlopban tört szám — nem kerekítünk, mert a kerekítés "
                "iránya üzleti döntés"
            ),
        )

    return Extracted(float(value), Confidence.CONFIRMED, evidence)


# ----------------------------------------------------------------------
# Dátum
# ----------------------------------------------------------------------


def _interpret_date(
    raw: Any, options: TabularOptions, evidence: Optional[SourceEvidence]
) -> Extracted[Any]:
    """Dátum — csak KIMONDOTT alakokat fogadunk el.

    A `nap/hónap/év` és a `hónap/nap/év` ugyanúgy néz ki, és a kettő
    összekeverése hónapokig működik, mert a hónap első 12 napján helyes
    eredményt ad. Ezért itt nincs heurisztika: ami nem illeszkedik a
    beállított alakokra, az hiány.
    """
    if isinstance(raw, _dt.datetime):
        return Extracted(raw.date(), Confidence.CONFIRMED, evidence)
    if isinstance(raw, _dt.date):
        return Extracted(raw, Confidence.CONFIRMED, evidence)

    text = str(raw).strip()
    for pattern in options.date_formats:
        try:
            parsed = _dt.datetime.strptime(text, pattern)
        except ValueError:
            continue
        return Extracted(parsed.date(), Confidence.CONFIRMED, evidence)

    return Extracted(
        value=None,
        confidence=Confidence.MISSING,
        evidence=evidence,
        note=(
            f"nem illeszkedik egyetlen beállított dátum-alakra sem "
            f"({options.date_formats}): {text!r}. Nem találgatunk — a "
            f"nap/hónap sorrend tévedése a hónap első 12 napján helyes "
            f"eredményt ad, ezért sokáig rejtve marad."
        ),
    )


# ----------------------------------------------------------------------
# Logikai
# ----------------------------------------------------------------------


def _interpret_boolean(
    raw: Any, options: TabularOptions, evidence: Optional[SourceEvidence]
) -> Extracted[Any]:
    if isinstance(raw, bool):
        return Extracted(raw, Confidence.CONFIRMED, evidence)

    text = str(raw).strip().casefold()
    if text in {value.casefold() for value in options.true_values}:
        return Extracted(True, Confidence.CONFIRMED, evidence)
    if text in {value.casefold() for value in options.false_values}:
        return Extracted(False, Confidence.CONFIRMED, evidence)

    return Extracted(
        value=None,
        confidence=Confidence.MISSING,
        evidence=evidence,
        note=(
            f"nem ismert logikai érték: {str(raw).strip()!r} "
            f"(igaz: {options.true_values}, hamis: {options.false_values})"
        ),
    )
