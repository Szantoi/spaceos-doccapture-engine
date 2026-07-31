"""Dokumentum szövegének beolvasása a MEGLÉVŐ szövegrétegből.

MI EZ ÉS MI NEM
---------------
Ez az út a **digitális** dokumentumé: a szöveg már ott van a fájlban, csak ki
kell olvasni — **modell nem kell**. Ha a szövegréteg hiányzik vagy kétértelmű,
ez az út **kimondott hiányt** ad, és NEM esik át csendben a felismerő útra
(az DC-03, és ma nem is létezik).

MIÉRT ITT VAN AZ ÚTVÁLASZTÁS
----------------------------
Se az adapteré nem lehet (nem tudja, mi a következő út), se a magé (nem nyithat
fájlt). A sorrend kötött, és mindegyik lépésnek oka van:

1. **Zaj-fájl kizárás (M12)** — biztonsági másolat és lock-fájl nem forrás.
2. **Kiterjesztés-útválasztás** — a config szerint; ha nem erre az útra jelölt,
   azt **kimondjuk**, nem próbáljuk meg mégis.
3. **A szövegréteg MÉRÉSE** — a kiterjesztés nem tudja megmondani, van-e
   szövegréteg; azt meg kell nézni.
4. **Fail-closed döntés** — csak a `USABLE` megy tovább.
5. **Olvasási sorrend + összeolvadás-jelzés (M2)** — determinisztikusan.
6. **Sorok + bizonyíték** — a `DocumentAnalyzer` bemeneti alakjában.

MIÉRT FAIL-CLOSED — MÉRT OKBÓL
------------------------------
A két hibairány nem egyenrangú:

- ha a kétértelmű réteget **igennek** vennénk: a kimenet **csendben téves**
  (a szkenner-bélyegző dokumentum-tartalomként jelenne meg);
- ha **nemnek** vesszük: a kimenet **kimondott hiány**, amit a hívó lát.

„Inkább hiány, mint téves" (M6) — a csendes tévedés drágább.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from doccapture.core.columns import (
    MergedColumnSuspicion,
    detect_merged_columns,
    reading_order,
)
from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.layout import PageLayout
from doccapture.core.models import InputKind, SourceEvidence
from doccapture.core.observability import get_logger, log_step
from doccapture.core.ports import TextLayerReader
from doccapture.core.source_selection import is_excluded, route_by_extension
from doccapture.infrastructure.evidence import evidence_for, resolve_source
from doccapture.infrastructure.textlayer.probe import (
    TextLayerMeasurement,
    measure_text_layer,
)
from doccapture.infrastructure.textlayer.reader import PdfiumTextLayerReader

_log = get_logger("read_document_text")


@dataclass
class DocumentTextResult:
    """Egy dokumentum kiolvasott szövege — a `DocumentAnalyzer` bemeneti alakjában.

    Miért nem közvetlenül `CaptureRecord`: ez a lépés még **nem elemzés**. A
    rekordot az elemző állítja elő; ha ez is rekordot adna, két helyen
    keletkezne ugyanaz, és az egyik előbb-utóbb elcsúszna.
    """

    lines: list[str]
    """Olvasási sorrendben. Ezt kapja a `DocumentAnalyzer`."""

    evidence: SourceEvidence
    """Fájl-szintű bizonyíték (relatív út + tartalom-hash, M13)."""

    pages: list[PageLayout] = field(default_factory=list)
    """A geometria megmarad — a hívó a lokátorhoz és a későbbi PDF-íráshoz kéri."""

    merged_column_suspicions: list[MergedColumnSuspicion] = field(default_factory=list)
    """M2: az összeolvadás-gyanús fragmensek. **Jelzés, nem szétvágás.**"""

    diagnostics: list[str] = field(default_factory=list)
    """Amit észrevettünk, de nem javítottunk."""

    @property
    def input_kind(self) -> InputKind:
        return InputKind.TEXT_LAYER_DOCUMENT


class DocumentTextReader:
    """Digitális dokumentum → szövegsorok + geometria + bizonyíték."""

    def __init__(
        self,
        config: Optional[CaptureConfig] = None,
        *,
        text_layer_reader: Optional[TextLayerReader] = None,
    ) -> None:
        """Az olvasó felülírható — teszthez és cserélhetőséghez egyaránt.

        Ha nem adják meg, a beépített adapter jön létre **lustán**: akinek csak
        a táblázatos út kell, ne bukjon el a hiányzó külső csomagon.
        """
        self._config = config or CaptureConfig()
        self._reader = text_layer_reader

    def read(self, relative_path: str) -> DocumentTextResult:
        """Beolvasás. A forrást csak OLVASSUK (M10) — semmit nem írunk mellé."""
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
        if kind is not InputKind.TEXT_LAYER_DOCUMENT:
            raise SourceUnreadableError(
                f"A(z) {relative_path!r} nem a szövegréteges útra van jelölve, "
                f"hanem a(z) {kind.value!r} útra. A négy bemenet négy külön út: "
                f"ezt a fájlt a saját útjának olvasója kezeli."
            )

        path = resolve_source(self._config.input_root, relative_path)
        measurement = measure_text_layer(path, self._config.text_layer)
        self._assert_usable(relative_path, measurement)

        reader = self._reader
        if reader is None:
            reader = self._reader = PdfiumTextLayerReader(self._config)
        pages = reader.read_pages(relative_path)

        diagnostics: list[str] = [f"szövegréteg-mérés: {measurement.reason}"]
        lines: list[str] = []
        suspicions: list[MergedColumnSuspicion] = []

        for page in pages:
            ordered = reading_order(page.fragments)
            # A geometria a lapon MARAD rendezve: aki kesobb a lapot hasznalja
            # (pl. a kereshető PDF irasa), ugyanazt a sorrendet lassa, mint aki
            # a sorokat olvassa. Ket kulon sorrend ket igazsag lenne.
            page.fragments = ordered
            lines.extend(fragment.text for fragment in ordered)

            page_suspicions = detect_merged_columns(page, self._config.text_layer)
            for suspicion in page_suspicions:
                diagnostics.append(
                    f"{page.source_name}: összeolvadás-gyanú — {suspicion.reason}"
                )
            suspicions.extend(page_suspicions)

        evidence = evidence_for(self._config.input_root, relative_path)
        log_step(
            _log,
            "document_text.read",
            source=relative_path,
            pages=len(pages),
            lines=len(lines),
            merged_suspicions=len(suspicions),
        )
        return DocumentTextResult(
            lines=lines,
            evidence=evidence,
            pages=pages,
            merged_column_suspicions=suspicions,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------

    def _assert_usable(
        self, relative_path: str, measurement: TextLayerMeasurement
    ) -> None:
        """Fail-closed: csak a `USABLE` megy tovább, és az elutasítás INDOKOLT.

        A hibaüzenet megmondja, mit mértünk és mihez képest — enélkül a hívó
        nem tudná eldönteni, hogy a küszöböt kell hangolni, vagy a fájl
        tényleg a raszteres útra való.
        """
        if measurement.usable:
            return
        raise SourceUnreadableError(
            f"A(z) {relative_path!r} szövegrétege nem használható "
            f"({measurement.verdict.value}): {measurement.reason}. "
            f"Ez az út NEM esik át csendben a felismerő útra — a raszteres "
            f"olvasás külön szelet, és ma nem elérhető. Ha a küszöb túl szigorú, "
            f"a `text_layer.min_usable_chars_per_page` állítható."
        )
