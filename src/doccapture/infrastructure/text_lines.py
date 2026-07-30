"""Szövegsorok beolvasása egy forrásfájlból.

Miért létezik ma: az irat-elemzés (DC-06) **szövegsorokból** dolgozik, bárhonnan
jöttek — de a szövegréteg- és a felismerő-adapter (DC-01) még nincs meg. Ez a
minimális olvasó teszi a láncot **végponttól végpontig futtathatóvá** már most,
egy sima szövegfájlon.

⚠ **Amit ez NEM helyettesít:** ez nem szövegréteg-kiolvasó és nem felismerő. Egy
dokumentumot **nem** nyit meg — csak azt, ami már szöveg. Ha ezt bárki
dokumentumra irányítja, szemetet fog kapni; a kiterjesztés-útválasztás ezért
kimondottan ellenőrzött a use-case-ben.

A kódolás-fegyelem **ugyanaz**, mint az elválasztott szöveges adapternél: jelöltek
sorrendben, kódlap-alapú kódolás nélkül — azok soha nem buknak el, tehát
elnyelnék a valódi kódolási hibát.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.models import SourceEvidence
from doccapture.core.observability import get_logger, log_step
from doccapture.infrastructure.evidence import evidence_for, resolve_source

_log = get_logger("text_lines")


class TextLineReader:
    """Sima szövegfájl → sorok + bizonyíték."""

    def __init__(self, config: Optional[CaptureConfig] = None) -> None:
        self._config = config or CaptureConfig()

    def read(self, relative_path: str) -> tuple[list[str], SourceEvidence]:
        """Sorok és a fájl-szintű bizonyíték. A forrást csak OLVASSUK (M10)."""
        path = resolve_source(self._config.input_root, relative_path)
        text = self._decode(path)
        # `splitlines()` es nem `split("\n")`: kezeli a CR/LF, CR es a Unicode
        # sortoreseket is. Egy CR-vegzodesu fajl `split("\n")`-nel EGY sor lenne,
        # es a cimke-kereses semmit nem talalna -- csendben.
        lines = text.splitlines()

        evidence = evidence_for(self._config.input_root, relative_path)
        log_step(
            _log,
            "text_lines.read",
            source=relative_path,
            lines=len(lines),
            non_empty=sum(1 for line in lines if line.strip()),
        )
        return lines, evidence

    def _decode(self, path: Path) -> str:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SourceUnreadableError(f"A fájl nem olvasható: {path.name} ({exc})") from exc

        attempted: list[str] = []
        for encoding in self._config.tabular.encoding_candidates:
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, LookupError) as exc:
                attempted.append(f"{encoding} ({type(exc).__name__})")

        raise SourceUnreadableError(
            f"Egyetlen kódolás-jelölttel sem dekódolható: {path.name}. "
            f"Megkísérelve: {attempted}."
        )
