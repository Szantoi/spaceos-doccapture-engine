"""Irat elemzése: típus-felismerés → mezők → önellenőrző számtan → rekord.

A LÁNC, ÉS MIÉRT EBBEN A SORRENDBEN
-----------------------------------
1. **Felismerés** — mi az irat. Ha ez nem sikerül, **megállunk**: egy rossz
   profillal kinyert mezők rosszabbak, mint a semmi, mert helyesnek látszanak.
2. **Mezők** — a profil szerint, címke → érték, bizonyítékkal.
3. **Önellenőrző számtan** — az irat önmagában stimmel-e (M3), és a hiányzó érték
   a hibára kevésbé érzékeny útról származtatva (M4).
4. **Rekord** — normalizált javaslat, megbízhatóság-jelöléssel.

⚠ **AHOL A MOTOR MEGÁLL — ÉS EZ NEM VÉLETLEN**
A rekord megmondja, **mi van a papíron**. Azt **nem**, hogy mi kerüljön a fogadó
rendszerbe: cikkszám-párosítás, mennyiség-átváltás, jóváhagyás **nincs itt**, és
nem is lesz. Az az iparági réteg dolga, ott determinisztikus szabály + ember
dönt, nem modell (G1/G2).

Ez az utolsó pont, ahol egy „segítő" párosítást be lehetne csúsztatni — ezért a
határt **teszt is őrzi**, nem csak ez a bekezdés.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from doccapture.core.config import CaptureConfig
from doccapture.core.documents.consistency import RuleOutcome, apply_rules
from doccapture.core.documents.detect import detect_profile
from doccapture.core.documents.extract import extract_fields
from doccapture.core.documents.profile import DocumentProfile
from doccapture.core.models import CaptureRecord, Confidence, Extracted, InputKind
from doccapture.core.observability import get_logger, log_step

_log = get_logger("documents")

PROFILE_FIELD = "document_profile"
"""A felismert irat-típus mező-kulcsa a rekordban.

Egy helyen definiált konstans: ha a fogyasztó ezt keresi, akkor **szerződés**, és
a szerződésnek egy forrása lehet.
"""


class DocumentAnalyzer:
    """Szövegsorokból irat-elemzés a profil-katalógus alapján."""

    def __init__(
        self,
        profiles: Iterable[DocumentProfile],
        config: Optional[CaptureConfig] = None,
    ) -> None:
        self._profiles = tuple(profiles)
        self._config = config or CaptureConfig()
        if not self._profiles:
            # Nem dobunk kivetelt: ures katalogussal a felismeres kimondott
            # hianyt ad, ami helyes viselkedes. De KIMONDJUK, mert egy ures
            # katalogus konnyen konfiguracios hiba.
            log_step(_log, "documents.empty_catalogue", profiles=0)

    @property
    def profiles(self) -> tuple[DocumentProfile, ...]:
        return self._profiles

    def analyze(
        self,
        lines: Sequence[str],
        *,
        input_kind: InputKind,
        evidence,
        line_locator: Optional[str] = None,
    ) -> CaptureRecord:
        """Egy irat elemzése. A bizonyítékot a hívó adja (ő olvasta a forrást)."""
        detection = detect_profile(lines, self._profiles, evidence)
        diagnostics: list[str] = list(detection.diagnostics)

        fields: dict[str, Extracted[Any]] = {PROFILE_FIELD: detection.profile}
        profile = detection.selected

        if profile is None:
            # MEGALLUNK. Egy rossz profillal kinyert mezo rosszabb, mint a semmi:
            # helyesnek latszik, es senki nem nezi meg.
            diagnostics.append(
                "az irat-típus nem eldönthető — mezőket NEM nyertünk ki, mert egy "
                "téves profil minden mezőt elrontana. Emberi besorolás kell."
            )
            log_step(
                _log,
                "documents.analyze",
                profile="nincs",
                confidence=detection.profile.confidence.value,
                candidates=len(detection.candidates),
                fields=0,
            )
            return CaptureRecord(
                input_kind=input_kind,
                evidence=evidence,
                fields=fields,
                diagnostics=diagnostics,
            )

        extracted, extract_notes = extract_fields(
            lines,
            profile,
            options=self._config.tabular,
            evidence=evidence,
            human_only_field_types=self._config.human_only_field_types,
            line_locator=line_locator,
        )
        diagnostics.extend(extract_notes)

        checked, outcomes = apply_rules(
            extracted, profile.rules, self._config.redundancy_tolerance
        )
        diagnostics.extend(_rule_notes(outcomes))

        fields.update(checked)

        log_step(
            _log,
            "documents.analyze",
            profile=profile.profile_id,
            confidence=detection.profile.confidence.value,
            candidates=len(detection.candidates),
            fields=len(checked),
            fields_missing=sum(
                1 for item in checked.values() if item.confidence is Confidence.MISSING
            ),
            rules=len(outcomes),
            rule_violations=sum(1 for o in outcomes if o.is_violation),
            derived=sum(1 for o in outcomes if o.status == "származtatva"),
        )

        return CaptureRecord(
            input_kind=input_kind,
            evidence=evidence,
            fields=fields,
            diagnostics=diagnostics,
        )


def _rule_notes(outcomes: list[RuleOutcome]) -> list[str]:
    """A szabály-kimenetek diagnosztikai alakja.

    A **sértéseket előre** tesszük: egy 20 elemű diagnosztika-listában az az egy
    sor a lényeg, és ha a végén van, nem olvassa el senki.
    """
    violations = [o for o in outcomes if o.is_violation]
    others = [o for o in outcomes if not o.is_violation]
    return [
        f"⚠ önellenőrzés BOMLIK — {o.rule_name}: {o.detail}" for o in violations
    ] + [f"önellenőrzés [{o.status}] {o.rule_name}: {o.detail}" for o in others]
