"""A motor hibafajtái.

Miért saját hierarchia: a hívó dönteni akar — újrapróbálható-e a művelet, vagy
végleges. Ha minden hiba `Exception`, ezt a döntést a hívó nem tudja meghozni,
és vagy mindent újrapróbál, vagy semmit.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations


class CaptureError(Exception):
    """Minden motor-hiba őse."""


class TransientError(CaptureError):
    """Átmeneti hiba — újrapróbálásnak VAN értelme (időtúllépés, ráta-korlát).

    A megkülönböztetés azért van a magban, mert ez DOMAIN-döntés: azt, hogy egy
    hiba átmeneti-e, az adapter tudja, de hogy mit KEZDÜNK vele, az itt dől el.
    """


class PermanentError(CaptureError):
    """Végleges hiba — az újrapróbálás csak időt és pénzt éget."""


class SourceUnreadableError(PermanentError):
    """A forrás nem olvasható vagy nem értelmezhető.

    Fontos: ez NEM ugyanaz, mint amikor egy mező hiányzik. A hiányzó mező
    `Confidence.MISSING`, azaz ADAT — nem kivétel. Kivételt csak akkor dobunk,
    ha magát a forrást nem tudtuk feldolgozni.
    """


class ConfigurationError(PermanentError):
    """A konfiguráció hiányos vagy ellentmondásos.

    Fail-fast: inkább induláskor bukjunk el, mint hogy egy hiányzó beállítás
    miatt csendben rossz eredményt adjunk.

    Ide tartozik a **hibás séma-leírás** is (üres kulcs, ismeretlen oszlop-típus,
    nem létező kulcsra hivatkozó szabály): az a beállításunk hibája, nem a
    forrásé — és a kettő szétválasztása azért fontos, mert az egyiket mi
    javítjuk, a másikat az ügyfél.
    """


class SchemaMismatchError(SourceUnreadableError):
    """A FORRÁS nem illeszkedik a sémára (hiányzó kötelező oszlop).

    Miért a `SourceUnreadableError` alatt: a séma rendben van, csak ez a fájl
    nem az, aminek hittük. A hívó ebből tudja, hogy **a fájlt** kell megnézni,
    nem a beállítást.
    """


class AmbiguousHeaderError(SchemaMismatchError):
    """A fejléc-illesztés kétértelmű: több oszlop illik ugyanarra a mezőre.

    Külön hibafajta, mert a helyes válasz IS más: itt nem a fájl rossz és nem is
    a séma hibás önmagában — a kettő **együtt** nem dönthető el. A javítás az
    elfogadott fejlécek pontosítása.

    Amiért egyáltalán kivétel: a kényelmes alternatíva („vedd az első illeszkedő
    oszlopot") működne, és épp ezért lenne veszélyes — a rossz oszlopból töltés
    hónapokig nem derülne ki.
    """
