"""A szövegréteges út beállításai — mikor HASZNÁLHATÓ egy szövegréteg.

Ezek domain-küszöbök, nem könyvtár-paraméterek: azt mondják meg, mit tekintünk
használható szövegrétegnek, nem azt, hogy az olvasó hogyan dolgozzon. Beágyazott
csomag a `core/tabular/options.py` precedense szerint: együtt alkotnak egy
értelmes egészt, és a fogyasztó egy úthoz EGY beállítás-csomagot ad át.

MIÉRT HÁROM ÁLLAPOT, NEM KETTŐ
------------------------------
A mért csapda: egy szkennelt lap, amin csak a szkenner lábléc-bélyegzője van,
22 karaktert ad 1 téglalapban. Egy `van-e karakter?` boolean ezt a bélyegzőt
dokumentum-tartalomnak minősítené, és a lap a szövegréteges úton menne tovább —
a valódi tartalma (a kép) pedig csendben elveszne. Ezért a verdikt háromállapotú:

- **használható** — elég érdemi karakter van (>= `min_usable_chars_per_page`);
- **kétértelmű** — van valami, de kevés (a sáv alja és a küszöb között): ez
  KIMONDOTT bizonytalanság, nem döntés — a hívó fail-closed módon kezeli;
- **nincs** — gyakorlatilag üres szövegréteg.

„Inkább hiány, mint téves": a kétértelmű eset nem eshet át csendben egyik
oldalra sem.

⚠ Egyetlen alapérték sem hordoz országot, nyelvet vagy írásrendszert.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from doccapture.core.errors import ConfigurationError


@dataclass
class TextLayerOptions:
    """A szövegréteg használhatóságának domain-küszöbei."""

    min_usable_chars_per_page: int = 32
    """Ennyi érdemi (nem üresköz) karaktertől HASZNÁLHATÓ egy lap szövegrétege.

    Az alapérték a mért csapda fölött áll: a szkenner-bélyegzős lap 22
    karaktere alatta marad, egy valódi (mérve 98 karakteres) tartalom-lap
    fölötte. Bevezetésenként hangolható — a helyes érték a forrás-rendszertől
    függ, nem a motortól.
    """

    ambiguous_chars_band: int = 1
    """Ettől a karakterszámtól a küszöbig a verdikt KÉTÉRTELMŰ, alatta NINCS.

    Az alapérték 1: már egyetlen érdemi karakter is „van ott valami" — azt nem
    minősítjük némán üresnek, hanem kimondott bizonytalanságnak. Aki 0-ra
    állítja... nem tudja: a validate() az 1-nél kisebb értéket elutasítja,
    mert a „nincs" és a „kétértelmű" összemosása pont a háromállapotúság
    értelmét szüntetné meg.
    """

    merged_span_ratio: float = 0.6
    """A lapszélesség ekkora hányadát átfogó fragmens ÖSSZEOLVADÁS-gyanús (M2).

    Szkennelt, hasábos elrendezésnél a szövegréteg gyakran egy sorba olvasztja
    a két hasábot. A gyanút JELÖLJÜK, nem vágjuk szét: a szétvágás horgonya
    profil-adat (M1), és egy elrendezés-szintű vágó-szabály két igazságot
    teremtene ugyanarról.
    """

    page_size_tolerance_pt: float = 3.0
    """Tűrés pontban, amikor a lapméretet egy deklarált fizikai mérethez mérjük.

    A mért ok: egy pixelben átadott lapméret ~4,17-szeres eltérést ad (mérve a
    forrás-prototípus lapján) — a tűrésnek ezt el KELL buktatnia, miközben a
    kerekítési különbséget (tört pont) átengedi.
    """

    def validate(self) -> None:
        """Fail-fast: az értelmetlen beállítás induláskor bukjon el.

        Ha egy hibás beállítás csak feldolgozás közben derül ki, akkor a hibát
        ott látjuk, ahol a hatása van, nem ott, ahol az oka.
        """
        if self.min_usable_chars_per_page < 1:
            raise ConfigurationError(
                f"A `min_usable_chars_per_page` legalább 1 kell legyen, "
                f"{self.min_usable_chars_per_page!r} nem az — 0-val minden üres "
                f"lap hasznalhatonak minősülne."
            )
        if self.ambiguous_chars_band < 1:
            raise ConfigurationError(
                "Az `ambiguous_chars_band` legalább 1 kell legyen: a NINCS és a "
                "KÉTÉRTELMŰ állapot összemosása a háromállapotú verdikt értelmét "
                "szüntetné meg."
            )
        if self.ambiguous_chars_band > self.min_usable_chars_per_page:
            raise ConfigurationError(
                f"Az `ambiguous_chars_band` ({self.ambiguous_chars_band}) nem lehet "
                f"nagyobb a `min_usable_chars_per_page`-nél "
                f"({self.min_usable_chars_per_page}) — a sáv a küszöb ALATT él."
            )
        if not 0 < self.merged_span_ratio <= 1:
            raise ConfigurationError(
                f"A `merged_span_ratio` a (0, 1] tartományban értelmes, "
                f"{self.merged_span_ratio!r} nem az. 0-val minden fragmens gyanús "
                f"lenne — egy detektor, ami mindig szól, megkülönböztethetetlen "
                f"attól, amelyik nem is fut."
            )
        if self.page_size_tolerance_pt < 0:
            raise ConfigurationError("A `page_size_tolerance_pt` nem lehet negatív.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TextLayerOptions":
        """Ismeretlen kulcsokat eldob (régebbi beállítás-fájlok miatt)."""
        known = cls.__dataclass_fields__.keys()
        options = cls(**{key: value for key, value in data.items() if key in known})
        options.validate()
        return options
