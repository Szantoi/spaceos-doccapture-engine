"""Melyik forrásfájlt vesszük fel egyáltalán — és melyiket hagyjuk ki.

Miért domain-döntés, és nem az adapter belügye: hogy egy biztonsági másolat
NEM forrás, az üzleti szabály, nem fájlrendszer-részlet. Ha az adapterben
lenne, minden új adapter újra eldöntené — és a harmadiknál valaki elfelejtené.

Az M12 mintából jön: minden éles mappában van `~$` kezdetű nyitott-fájl jelző,
`.bak` mentés és szerkesztő-lock. A kizárási lista **konfiguráció**, mert
rendszerenként más — de az alapértelmezés fedje a leggyakoribbakat, különben
minden bevezetés ugyanazzal a felfedezéssel kezdődik.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ) — az `fnmatch`
és a `posixpath` a szabványkönyvtár része, nem infrastruktúra: nem nyúlnak
fájlrendszerhez, csak szöveget hasonlítanak.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Optional

from doccapture.core.errors import ConfigurationError
from doccapture.core.models import InputKind


def is_excluded(relative_path: str, patterns: list[str]) -> bool:
    """Zaj-fájl-e a megadott minták szerint.

    A mintát a **fájlnévre** és a **teljes relatív útra** is illesztjük: a
    `~$*` fájlnévre való, a `*/gyorsitotar/*` útra. Ha csak az egyiket néznénk,
    a másik fajta minta csendben soha nem fogna.
    """
    normalized = relative_path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    return any(fnmatch(name, p) or fnmatch(normalized, p) for p in patterns)


def route_by_extension(
    relative_path: str, routing: dict[str, InputKind]
) -> Optional[InputKind]:
    """Kiterjesztés → a bemenet FELTÉTELEZETT útja. `None` = nem támogatott.

    ⚠ **Feltételezés, nem tény.** A `.pdf`-nél csak megnézve tudható meg, van-e
    szövegréteg; ha nincs, a fázis a raszteres útra vált. A táblázatos és a
    képi kiterjesztéseknél a jelölés megbízható.
    """
    normalized = relative_path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1]
    if "." not in name:
        return None
    suffix = "." + name.rsplit(".", 1)[-1]
    return routing.get(suffix.lower())


def require_relative(path: str) -> str:
    """Elbukik, ha az útvonal nem relatív.

    Miért kapu: a `SourceEvidence` szerződése szerint abszolút út **nem
    tárolható** — az felfedi a gépi könyvtárszerkezetet, és a bizonyíték
    átvihetetlen lesz egy másik telepítésre. Egy szabály, amit nem mér senki,
    előbb-utóbb megsérül.
    """
    normalized = path.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
        raise ConfigurationError(
            f"Abszolút útvonal nem tárolható bizonyítékként: {path!r}. "
            f"A bemeneti gyökérhez képest relatív utat adj."
        )
    if ".." in normalized.split("/"):
        raise ConfigurationError(
            f"A relatív útvonal kilép a bemeneti gyökérből: {path!r}."
        )
    return normalized
