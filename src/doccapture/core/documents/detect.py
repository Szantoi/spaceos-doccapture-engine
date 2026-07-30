"""Irat-típus felismerése — BIZONYÍTÉKKAL, nem valószínűséggel.

MIÉRT NINCS ITT MODELL
----------------------
Egy osztályozó azt mondja meg, *mennyire hasonlít* az irat valamire. Nekünk azt
kell tudnunk, hogy **mi van rajta** — és ez horgony-alapon **eldönthető**. Egy
osztályozó tippje nem auditálható; egy megtalált horgony igen. Ugyanaz az elv,
mint hogy cikkszámot nem tippel modell.

A LEGFONTOSABB SZABÁLY: HOLTVERSENYNÉL NEM DÖNTÜNK
--------------------------------------------------
Ha rossz profilt választunk, **nem egy mező lesz hibás, hanem az egész
elemzés** — és úgy fog kinézni, mint egy sikeres feldolgozás. Ez a legdrágább
néma hiba, amit ez a réteg okozhat. Ezért:

| Eset | Megbízhatóság |
|---|---|
| pontosan egy profil illeszkedik | `CONFIRMED` |
| több illeszkedik, de van **szigorúan legjobb** | `NEEDS_REVIEW` |
| **holtverseny** | `MISSING` — nem választunk |
| egyik sem illeszkedik | `MISSING` — „nem tudom" érvényes válasz |

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field as _field
from typing import Iterable, Optional

from doccapture.core.models import Confidence, Extracted, SourceEvidence
from doccapture.core.documents.profile import DocumentProfile


@dataclass(frozen=True)
class ProfileMatch:
    """Egy profil illeszkedésének mérlege — hogy a döntés megmagyarázható legyen."""

    profile: DocumentProfile
    matched_required: tuple[str, ...] = ()
    matched_optional: tuple[str, ...] = ()
    missing_required: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        """Jelölt-e egyáltalán: MINDEN kötelező horgonya megvan."""
        return not self.missing_required

    @property
    def score(self) -> int:
        """A megtalált bizonyítékok száma. Nem valószínűség — **darabszám**."""
        return len(self.matched_required) + len(self.matched_optional)


@dataclass
class DetectionResult:
    """A felismerés eredménye a teljes mérleggel.

    Szándékosan hordozza az **összes** jelöltet, nem csak a győztest: egy
    „miért ezt választotta?" kérdésre másképp nem lehet válaszolni.
    """

    profile: Extracted[str]
    """A profil azonosítója, megbízhatósággal. `MISSING` = nem tudjuk."""

    candidates: tuple[ProfileMatch, ...] = ()
    diagnostics: list[str] = _field(default_factory=list)

    @property
    def selected(self) -> Optional[DocumentProfile]:
        """A kiválasztott profil objektum, vagy `None`, ha nem döntöttünk."""
        if self.profile.value is None:
            return None
        for match in self.candidates:
            if match.profile.profile_id == self.profile.value:
                return match.profile
        return None


def normalize_text(text: str) -> str:
    """Összehasonlítható alak a horgony-kereséshez.

    Kisbetűsítés + szóköz-összevonás + **ékezet-hajtogatás**. Itt az utóbbi
    szándékosan BE van kapcsolva — szemben a táblázat fejléc-illesztésével, és a
    különbség indoka fontos:

    - **fejlécnél** az összevonás két külön oszlopot olvaszthat egybe, abból
      kétértelműség lesz, és a betöltés elbukik ott, ahol addig működött;
    - **horgonynál** viszont a szöveg **felismerésből** jön, ahol az ékezet a
      leggyakoribb hibaforrás. Ha nem hajtogatnánk, a horgony egy hibás ékezet
      miatt nem találna — és a **teljes iratot** nem ismernénk fel.

    A két helyen tehát nem ugyanaz a helyes válasz, és ez nem következetlenség.
    """
    folded = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(without_accents.split()).casefold()


def detect_profile(
    lines: Iterable[str],
    profiles: Iterable[DocumentProfile],
    evidence: Optional[SourceEvidence] = None,
) -> DetectionResult:
    """Melyik profil illeszkedik az irat szövegére."""
    haystack = normalize_text(" \n ".join(lines))
    catalogue = list(profiles)

    matches: list[ProfileMatch] = []
    for profile in catalogue:
        required_hits = tuple(a for a in profile.required_anchors if _contains(haystack, a))
        matches.append(
            ProfileMatch(
                profile=profile,
                matched_required=required_hits,
                matched_optional=tuple(
                    a for a in profile.optional_anchors if _contains(haystack, a)
                ),
                missing_required=tuple(
                    a for a in profile.required_anchors if a not in required_hits
                ),
            )
        )

    eligible = [m for m in matches if m.eligible]
    diagnostics = _diagnostics(catalogue, matches, eligible)

    if not eligible:
        return DetectionResult(
            profile=Extracted(
                value=None,
                confidence=Confidence.MISSING,
                evidence=evidence,
                note=(
                    f"egyetlen profil horgonyai sem illeszkednek "
                    f"({len(catalogue)} profil megvizsgálva) — emberi besorolás kell"
                ),
            ),
            candidates=tuple(matches),
            diagnostics=diagnostics,
        )

    top = max(m.score for m in eligible)
    best = [m for m in eligible if m.score == top]

    if len(best) > 1:
        # NEM valasztunk: a rossz profil MINDEN mezot elrontana, es ugy nezne ki,
        # mint egy sikeres feldolgozas.
        return DetectionResult(
            profile=Extracted(
                value=None,
                confidence=Confidence.MISSING,
                evidence=evidence,
                note=(
                    "holtverseny a profilok között: "
                    + ", ".join(sorted(m.profile.profile_id for m in best))
                    + f" (mindegyik {top} horgonnyal). Nem választunk — a téves "
                    f"irat-típus az egész elemzést elrontaná."
                ),
            ),
            candidates=tuple(matches),
            diagnostics=diagnostics,
        )

    winner = best[0]
    egyertelmu = len(eligible) == 1
    return DetectionResult(
        profile=Extracted(
            value=winner.profile.profile_id,
            confidence=Confidence.CONFIRMED if egyertelmu else Confidence.NEEDS_REVIEW,
            evidence=evidence,
            note=(
                None
                if egyertelmu
                else (
                    f"több profil is illeszkedett; a legtöbb bizonyítékkal "
                    f"({winner.score}) ez nyert, de az ember nézze meg"
                )
            ),
        ),
        candidates=tuple(matches),
        diagnostics=diagnostics,
    )


def _contains(haystack: str, anchor: str) -> bool:
    normalized = normalize_text(anchor)
    return bool(normalized) and normalized in haystack


def _diagnostics(
    catalogue: list[DocumentProfile],
    matches: list[ProfileMatch],
    eligible: list[ProfileMatch],
) -> list[str]:
    """A döntés mérlege — hogy a „miért ezt?" kérdésre legyen válasz."""
    notes = [f"{len(catalogue)} profil megvizsgálva, {len(eligible)} jelölt"]
    for match in sorted(matches, key=lambda m: (-m.score, m.profile.profile_id)):
        allapot = "jelölt" if match.eligible else "kizárva"
        reszletek = f"horgony {match.score}"
        if match.missing_required:
            reszletek += f", hiányzó kötelező: {list(match.missing_required)}"
        notes.append(f"  {match.profile.profile_id}: {allapot} ({reszletek})")
    return notes
