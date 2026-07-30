"""Naplózás — hogy a futó kódról látszódjon, végigment-e (QUALITY §3).

MIÉRT NEM ELÉG EGY `logging.getLogger(__name__)`
------------------------------------------------
Egy napló, ami mindent kiír, **két új problémát** csinál:

1. **Abszolút útvonal a naplóban** = a gépi könyvtárszerkezet felfedése. A
   `SourceEvidence` szerződése szerint abszolút út **nem tárolható** — értelmetlen
   lenne a bizonyítékból kihagyni, aztán a log-fájlba beírni.
2. **Cella-érték a naplóban** = üzleti adat egy olyan fájlban, aminek gyakran
   lazább a hozzáférés-védelme, mint az adatbázisnak. Egy beszállítói ár vagy egy
   partner-azonosító nem tartozik a naplóba.

Ezért a napló **szerkezetről és darabszámról** beszél, nem tartalomról:
*„3 sor beolvasva, 1 kihagyva, 2 mező hiányos"* — és nem az, hogy **mi** volt
bennük. A hibakereséshez a darabszám és a **hely** (relatív út + lokátor) elég;
ha valakinek a tartalom kell, nyissa meg a forrást, ahová a bizonyíték mutat.

**Ezt teszt őrzi, nem figyelem** (`tests/test_observability.py`): a kapu
megvizsgálja, hogy a napló-hívások nem adnak-e át abszolút utat vagy
titok-sejtő kulcsot.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ) — a `logging` a
szabványkönyvtár része, és a mag **nem konfigurálja** a naplózást, csak használja.
A célt (fájl, gyűjtő, formátum) a beágyazó alkalmazás állítja be; egy könyvtár,
ami magához ragadja a gyökér-naplózót, elveszi a döntést a fogyasztótól.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

LOGGER_NAME = "doccapture"
"""A napló-fa gyökere. Egy helyen definiálva, hogy a fogyasztó **egy** névvel
tudja beállítani vagy elhallgattatni az egész motort."""

# Kulcs-nevek, amiket a naplo NEM vihet at. Ugyanaz a lista, mint a configban --
# de itt SZANDEKOSAN ujra kimondva: ha a ket helyen elcsuszik, az egyik elobb-utobb
# hazudni fog, ezert TESZT koti ossze a kettot.
_FORBIDDEN_KEY_HINTS = ("key", "secret", "token", "password", "credential")

# Ertek-alakok, amik abszolut utra utalnak. Nem tartalom-vizsgalat: alak-vizsgalat.
_ABSOLUTE_PATH_MARKERS = ("/", "\\")


class RedactionError(ValueError):
    """A napló olyan adatot kapott, amit nem vihet ki.

    Miért kivétel és nem csendes kihagyás: ha csendben elhagynánk a mezőt, a
    fejlesztő azt hinné, naplózott — és a hiba akkor derülne ki, amikor épp
    kellene a napló. Fail-fast: a hibás napló-hívás **fejlesztési hiba**, és
    a tesztben bukjon el, ne éles üzemben hallgasson.
    """


def get_logger(name: str = "") -> logging.Logger:
    """Napló a motor fa-nevével. `name` = a modul rövid neve, nem a teljes útja."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def assert_safe_fields(fields: Mapping[str, Any]) -> None:
    """Elbukik, ha a napló-mezők titkot vagy abszolút utat vinnének ki.

    Két külön szabály, mert két külön kár:

    - **titok-sejtő kulcs**: a *kulcs neve* alapján tiltunk, nem az értéke
      alapján — az érték felismerése találgatás, a kulcs neve nem;
    - **abszolút út**: az *alak* alapján tiltunk. A `relative_path` mező
      szándékosan **átmegy**, ha valóban relatív.
    """
    for key, value in fields.items():
        lowered = key.lower()
        if any(hint in lowered for hint in _FORBIDDEN_KEY_HINTS):
            raise RedactionError(
                f"A(z) {key!r} napló-mező titkot sejtet. A napló szerkezetről és "
                f"darabszámról beszél, nem tartalomról — a titok soha nem kerül ki."
            )
        if isinstance(value, str) and _looks_absolute(value):
            raise RedactionError(
                f"A(z) {key!r} napló-mező abszolút útnak látszik ({value[:24]!r}…). "
                f"A naplóba a bemeneti gyökérhez képest RELATÍV út kerül — az "
                f"abszolút út felfedi a gépi könyvtárszerkezetet."
            )


def _looks_absolute(value: str) -> bool:
    """Abszolút útnak látszik-e. Alak-vizsgálat, nem fájlrendszer-kérdés."""
    if value.startswith(("/", "\\")):
        return True
    # Windows-meghajto: "C:\..." vagy "C:/..."
    if len(value) > 2 and value[1] == ":" and value[2] in _ABSOLUTE_PATH_MARKERS:
        return True
    return False


def log_step(
    logger: logging.Logger,
    step: str,
    /,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Egy feldolgozási lépés naplózása — **ellenőrzött** mezőkkel.

    A hívás alakja szándékosan kötött (`lépés` + kulcs-érték mezők), nem szabad
    szöveg: így a napló **gépileg feldolgozható** (QUALITY §2 — „ha gépnek
    tervezünk, a kimenet legyen könnyen parszolható"), és a kapu meg tudja
    vizsgálni, mit viszünk ki.

    Példa a kimenetre:
        `tabular.read rows=3 skipped_blank=1 source=arlista.csv`
    """
    assert_safe_fields(fields)
    if not logger.isEnabledFor(level):
        # A `%`-formazas amugy is kesleltet, de a mezo-osszefuzest is megtakaritjuk:
        # egy 5000 soros betoltesnel a napolatlan szint is fizetne erte.
        return
    payload = " ".join(f"{key}={_render(value)}" for key, value in fields.items())
    logger.log(level, "%s %s", step, payload) if payload else logger.log(level, "%s", step)


def _render(value: Any) -> str:
    """Napló-alak: rövid, egy szó, idézőjel nélkül ahol lehet."""
    if isinstance(value, bool):
        return "igen" if value else "nem"
    text = str(value)
    return text if " " not in text else f'"{text}"'
