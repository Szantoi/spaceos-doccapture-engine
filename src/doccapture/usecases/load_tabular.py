"""Táblázatos forrás betöltése `CaptureRecord`-dá.

MI A HATÁR, AMIT EZ A USE-CASE ŐRIZ
-----------------------------------
A motor eddig jut el: **megmondja, mi van a táblázatban**. Azt NEM, hogy mi
kerüljön a fogadó rendszerbe — a cikkszám-párosítás, a mennyiség-átváltás és a
jóváhagyás a fogyasztóé, és ott determinisztikus szabály + ember dönt, nem
modell. Ez a **G1/G2 határ**, és itt van a helye, mert ez az utolsó pont, ahol
még bele lehetne csúsztatni egy „segítő" párosítást.

AMIT EZ A RÉTEG AD AZ ADAPTEREKHEZ KÉPEST
-----------------------------------------
1. **Útválasztás:** melyik adapter olvassa a fájlt (a config kiterjesztés-
   térképéből). Ha egy kiterjesztés nem táblázatos útra van jelölve, azt
   **kimondjuk** — nem próbáljuk meg mégis táblázatként olvasni.
2. **Zaj-fájl kizárás (M12):** biztonsági másolat és lock-fájl nem forrás.
3. **Mértékegység mint adat (M15):** a fejlécből felismert egység a rekord
   `unit:<kulcs>` mezőjébe kerül, a fejléc-cella bizonyítékával.
4. **Egy rekord = egy forrásfájl**, saját bizonyíték-lánccal (M13).
"""

from __future__ import annotations

from typing import Optional

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.models import (
    CaptureRecord,
    Confidence,
    Extracted,
    InputKind,
)
from doccapture.core.ports import TabularReader
from doccapture.core.source_selection import is_excluded, route_by_extension
from doccapture.core.tabular.schema import TableSchema
from doccapture.infrastructure.evidence import evidence_for, with_locator
from doccapture.infrastructure.tabular.delimited import DelimitedTabularReader
from doccapture.infrastructure.tabular.workbook import WorkbookTabularReader

UNIT_FIELD_PREFIX = "unit:"
"""A mértékegység-mezők előtagja a rekord `fields` szótárában.

Egy helyen definiált konstans és nem szétszórt szövegliterál: ha a fogyasztó
ezt keresi, akkor ez **szerződés**, és a szerződésnek egy forrása lehet.
"""

# Kiterjesztes -> adapter. Azert itt es nem a configban, mert ez NEM ugyfel-
# beallitas: az, hogy egy munkafuzetet melyik kodunk olvas, a mi implementacios
# dontesunk. A configban az all, hogy egy kiterjesztes MELYIK UTRA megy.
_WORKBOOK_EXTENSIONS = (".xlsx", ".xlsm", ".xltx", ".xltm")


class TabularLoader:
    """Egy táblázatos forrásfájlból `CaptureRecord`-ot állít elő."""

    def __init__(
        self,
        config: Optional[CaptureConfig] = None,
        *,
        delimited_reader: Optional[TabularReader] = None,
        workbook_reader: Optional[TabularReader] = None,
    ) -> None:
        """Az olvasók felülírhatók — teszthez és cserélhetőséghez egyaránt.

        Ha nem adják meg, a beépített adaptereket használjuk. A munkafüzet-olvasó
        **lustán** jön létre: ha valakinek csak a szöveges út kell, ne bukjon el
        a hiányzó külső csomagon.
        """
        self._config = config or CaptureConfig()
        self._delimited = delimited_reader
        self._workbook = workbook_reader

    def load(self, relative_path: str, schema: TableSchema) -> CaptureRecord:
        """Betöltés. A forrást csak OLVASSUK (M10) — semmit nem írunk mellé."""
        if is_excluded(relative_path, self._config.excluded_name_patterns):
            raise SourceUnreadableError(
                f"A fájl a kizárási listán van (zaj-fájl): {relative_path!r}. "
                f"Minta-lista: {self._config.excluded_name_patterns}"
            )

        kind = route_by_extension(relative_path, self._config.extension_routing)
        if kind is None:
            raise SourceUnreadableError(
                f"Nem támogatott kiterjesztés: {relative_path!r}. Támogatott: "
                f"{sorted(self._config.extension_routing)}"
            )
        if kind is not InputKind.TABULAR:
            # Kimondjuk, nem probaljuk meg megis. Egy PDF-et tablazatkent olvasni
            # nem hibat ad, hanem SZEMETET -- es a szemet ugy nez ki, mint adat.
            raise SourceUnreadableError(
                f"A(z) {relative_path!r} nem a táblázatos útra van jelölve, hanem "
                f"a(z) {kind.value!r} útra. A négy bemenet négy külön út: ezt a "
                f"fájlt a saját útjának olvasója kezeli."
            )

        reader = self._reader_for(relative_path)
        result = reader.read(relative_path, schema)

        file_evidence = evidence_for(self._config.input_root, relative_path)
        fields: dict[str, Extracted[object]] = {}
        for key, unit in result.units.items():
            # A mertekegyseg BIZONYITEKA a fejlec-cella: onnan olvastuk ki.
            # Igy egy kesobbi vitanal megmutathato, hogy nem feltettuk, hanem
            # a forrasban ott allt.
            fields[f"{UNIT_FIELD_PREFIX}{key}"] = Extracted(
                value=unit,
                confidence=Confidence.CONFIRMED,
                evidence=with_locator(
                    file_evidence, result.header_evidence_locator or "fejléc"
                ),
                note="a fejlécből felismert mértékegység — NEM átváltva (M15)",
            )

        return CaptureRecord(
            input_kind=InputKind.TABULAR,
            evidence=file_evidence,
            fields=fields,
            rows=result.rows,
            diagnostics=list(result.diagnostics),
        )

    # ------------------------------------------------------------------

    def _reader_for(self, relative_path: str) -> TabularReader:
        name = relative_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if name.endswith(_WORKBOOK_EXTENSIONS):
            if self._workbook is None:
                self._workbook = WorkbookTabularReader(self._config)
            return self._workbook
        if self._delimited is None:
            self._delimited = DelimitedTabularReader(self._config)
        return self._delimited
