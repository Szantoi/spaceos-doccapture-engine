"""Profil-katalógus betöltése lemezről.

Miért az infrastruktúrában: ez az egyetlen hely, ahol fájlt olvasunk a
profilokhoz. A mag a profil **alakját** ismeri, azt nem, hogy honnan jön — így a
katalógus lehet könyvtár, adatbázis vagy távoli szolgáltatás anélkül, hogy a
domain változna.

**A betöltés fail-fast:** egy hibás profil-leírás **induláskor** bukjon el, ne
akkor, amikor egy irat épp rá illeszkedne. Ha csak az adott profil olvasásakor
buknánk el, a hiba hetekkel később, egy véletlen iratnál jelenne meg.

⚠ **Az azonosító-ütközés HIBA, nem felülírás.** Két azonos `profile_id` esetén
elbukunk: a néma felülírás azt jelentené, hogy a katalógus tartalma a fájlok
olvasási sorrendjétől függ — és a sorrend fájlrendszerenként más.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from doccapture.core.documents.profile import DocumentProfile
from doccapture.core.errors import ConfigurationError
from doccapture.core.observability import get_logger, log_step

_log = get_logger("profiles")

PROFILE_SUFFIX = ".json"


def load_profiles(directory: str | Path) -> tuple[DocumentProfile, ...]:
    """Minden profil egy könyvtárból, névsorrendben.

    A névsorrend nem esztétika: **reprodukálható** katalógust ad, tehát a
    felismerés eredménye nem függ a fájlrendszer felsorolási sorrendjétől.
    """
    root = Path(directory)
    if not root.is_dir():
        raise ConfigurationError(f"A profil-könyvtár nem létezik: {directory!r}")

    profiles: list[DocumentProfile] = []
    seen: dict[str, str] = {}

    for path in sorted(root.glob(f"*{PROFILE_SUFFIX}")):
        profile = load_profile(path)
        if profile.profile_id in seen:
            raise ConfigurationError(
                f"Két profil ugyanazzal az azonosítóval: {profile.profile_id!r} "
                f"({seen[profile.profile_id]} és {path.name}). Nem írjuk felül "
                f"csendben — a katalógus tartalma a fájlok sorrendjétől függne."
            )
        seen[profile.profile_id] = path.name
        profiles.append(profile)

    log_step(_log, "profiles.load", directory=root.name, profiles=len(profiles))
    if not profiles:
        # Nem kivetel: ures katalogussal a felismeres kimondott hianyt ad. De
        # kimondjuk, mert ez szinte mindig konfiguracios hiba.
        log_step(_log, "profiles.empty", directory=root.name)
    return tuple(profiles)


def load_profile(path: str | Path) -> DocumentProfile:
    """Egy profil betöltése. A hibaüzenet **megnevezi a fájlt**.

    Miért fontos: egy tíz profilos katalógusban a „hiányzó `labels` mező"
    üzenet önmagában használhatatlan — nem tudod, melyik fájlt nyisd meg.
    """
    file_path = Path(path)
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigurationError(f"A profil nem olvasható: {file_path.name} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"A profil nem érvényes leírás: {file_path.name} "
            f"({exc.msg}, {exc.lineno}. sor)"
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigurationError(f"A profil gyökere nem objektum: {file_path.name}")

    try:
        return DocumentProfile.from_dict(raw)
    except ConfigurationError as exc:
        # Ujradobjuk a FAJLNEVVEL: kulonben nem tudod, melyik fajlt nyisd meg.
        raise ConfigurationError(f"{file_path.name}: {exc}") from exc


def select_profiles(
    profiles: Iterable[DocumentProfile], enabled: Optional[Iterable[str]] = None
) -> tuple[DocumentProfile, ...]:
    """Szűkítés engedélyezett azonosítókra. `None` = mind.

    Miért van rá szükség: egy telepítésen nem minden irat-típus fordul elő, és a
    **nem használt profil zaj** — ráadásul növeli a holtverseny esélyét a
    felismerésben. A szűkítés tehát nem optimalizálás, hanem pontosság.

    Az ismeretlen azonosító **hiba**: egy elgépelt profil-név csendben azt
    jelentené, hogy egy irat-típust soha nem ismerünk fel.
    """
    catalogue = tuple(profiles)
    if enabled is None:
        return catalogue

    wanted = list(enabled)
    known = {p.profile_id for p in catalogue}
    unknown = sorted(set(wanted) - known)
    if unknown:
        raise ConfigurationError(
            f"Ismeretlen profil-azonosító: {unknown}. Elérhető: {sorted(known)}. "
            f"Egy elgépelt név csendben azt jelentené, hogy azt az irat-típust "
            f"soha nem ismerjük fel."
        )
    return tuple(p for p in catalogue if p.profile_id in set(wanted))
