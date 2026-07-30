"""A táblázatos út beállításai — MINDEN, ami fájlonként/bevezetésenként más.

Miért külön dataclass és nem lapos mezők a `CaptureConfig`-ban: ezek együtt
alkotnak egy értelmes egészt (egy táblázat olvasási módja), és így a fogyasztó
egy táblázathoz **egy** beállítás-csomagot ad át. Laposan szétszórva a
`CaptureConfig` húsz mezővel hízna, és nem látszana, hogy melyik melyikkel függ
össze.

⚠ **Egyetlen alapérték sem hordoz országot, nyelvet vagy írásrendszert.** Ahol
üres az alapérték, az azt jelenti: „nincs megadva" — nem azt, hogy „angol" vagy
„magyar". Egy beégetett locale itt ugyanaz a hiba lenne, mint egy beégetett
cégnév: a termék egyetlen ügyfélnél lenne használható.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from doccapture.core.errors import ConfigurationError

# Karakterek, amik EGYETLEN irasrendszerben sem tizedesjelek -- ezert biztonsagos
# oket alapbol csoport-jelnek venni. A "." es a "," SZANDEKOSAN nincs itt: azok
# ketertelmuek, es a `values.py` ketertelmuseg-szabalya kezeli oket.
# Escape-kel es nem a karakterrel: a torhetetlen szokozok a forraskodban
# megkulonboztethetetlenek a kozonseges szokoztol, tehat egy szerkeszto vagy egy
# masolas csendben kicserelhetne oket -- es a csoport-jel eltunese nem bukna el
# semmin. Ezt teszt is orzi.
_UNAMBIGUOUS_GROUP_SEPARATORS = [
    " ",       # U+0020 kozonseges szokoz
    "\u00a0",  # torhetetlen szokoz
    "\u202f",  # keskeny torhetetlen szokoz
    "\u2009",  # keskeny szokoz
    "'",       # aposztrof (svajci csoportositas)
]

# ISO-8601. Nem locale, hanem szabvany -- ez az egyetlen datum-alak, amit
# alapertelmezesben felismerunk. Minden tovabbi alak konfiguracio.
_ISO_DATE_FORMAT = "%Y-%m-%d"


@dataclass
class TabularOptions:
    """Egy táblázatos forrás olvasási módja."""

    # --- Hol van a fejléc és hol kezdődik az adat ---
    header_row: int = 1
    """A fejléc sorának száma, 1-alapon.

    A prototípus ezt beégette (`range(2, …)` = fejléc az 1. sorban). Valós
    fájlokban van előtte címsor, üres sor vagy logó — és akkor a betöltés az
    első sortól kezdve rosszul kötődik, csendben.
    """

    data_starts_after_header: int = 0
    """Hány sort hagyjunk ki KÖZVETLENÜL a fejléc után.

    Tipikus eset: a fejléc alatt egy mértékegység-sor vagy egy példa-sor áll.
    Ha ezt nem hagyjuk ki, az első adatsor szemét lesz — és mivel csak egy sor,
    könnyen átcsúszik a szemrevételezésen.
    """

    sheet_name: str = ""
    """Melyik lapot olvassuk. `""` = az aktív lap.

    Az aktív lap **mentéskor változik**, tehát a `""` kényelmes, de nem stabil.
    Aki reprodukálható betöltést akar, nevezze meg a lapot.
    """

    max_rows: int = 0
    """Legfeljebb ennyi adatsor. `0` = nincs korlát.

    Ha a korlát ELÉRHETŐ, a betöltés azt **kimondja** a diagnosztikában — egy
    néma csonkolás úgy néz ki, mint egy hiánytalan betöltés.
    """

    # --- Elválasztott szöveg (a munkafüzetnél nem használt) ---
    delimiter: str = ""
    """Az elválasztó karakter. `""` = felismerés a fájl elejéből.

    Ha a felismerés nem sikerül, **kimondott hibát** dobunk, nem tippelünk
    vesszőre: egy rossz elválasztóval a teljes fájl egyetlen oszlop lesz, és a
    séma-illesztés amúgy is elbukna — de értelmezhetetlen hibaüzenettel.
    """

    delimiter_candidates: list[str] = field(
        default_factory=lambda: [";", ",", "\t", "|"]
    )
    """Amik közül a felismerés VÁLASZTHAT, ha a `delimiter` nincs megadva.

    ⚠ **Ezt a mezőt egy bukó teszt hozta létre, és a lelet a mérőeszközről
    szólt.** A szabványkönyvtár felismerője **nem bukik el**, ha nem tudja
    eldönteni — hanem **tippel**. Egy elválasztó nélküli soron a **szóközt**
    választotta, és a fejléc szavakra esett szét: a betöltés „működött", csak
    éppen szemetet adott.

    Ezért a jelöltek listája zárt, és a szóköz **nincs** benne: egy szöveges
    mezőben szóköz mindig van, tehát az soha nem lehet biztonságos jelölt.
    """

    encoding_candidates: list[str] = field(
        default_factory=lambda: ["utf-8-sig", "utf-8"]
    )
    """Kódolás-jelöltek, sorrendben. Az első, amivel a fájl dekódolható, nyer.

    Szándékosan nincs benne kódlap-alapú kódolás: azok **soha nem buknak el**
    (minden bájt-sorozat érvényes bennük), tehát ha a listába kerülnek, elnyelik
    a valódi kódolási hibát, és ékezet helyett szemetet kapunk — csendben.
    Aki ilyen forrást olvas, vegye fel, de tudja, hogy a hibajelzést cseréli el
    kényelemre.
    """

    # --- Fejléc-illesztés ---
    header_match_casefold: bool = True
    """Kis-nagybetű elhanyagolása a fejléc-illesztésben.

    Biztonságos: nincs olyan táblázat, ahol a „Mennyiség" és a „MENNYISÉG" két
    külön oszlop akarna lenni.
    """

    header_match_strip_accents: bool = False
    """Ékezet-hajtogatás a fejléc-illesztésben. Alapból KI.

    Miért ki: az összevonás **két különböző** fejlécet egybe olvaszthat, és
    abból kétértelműség lesz — a betöltés pedig elbukik ott, ahol addig működött.
    Aki bekapcsolja, tudja, mit vállal.
    """

    unit_bracket_pairs: list[str] = field(default_factory=lambda: ["()", "[]"])
    """Zárójel-párok, amikben a fejléc mértékegységet hordozhat (`Hossz (mm)`).

    Két karakterből álló sztringek: nyitó + záró.
    """

    # --- Érték-értelmezés ---
    decimal_separator: str = ""
    """A tizedesjel. `""` = nincs megadva → az adatból, kétértelműségnél HIÁNY.

    Ha meg van adva, a kétértelműség eltűnik. Az üres alapérték nem lustaság:
    egy beégetett tizedesjel a számok tízszeresét vagy ezredét adná egy másik
    írásrendszerű ügyfélnél, és **semmi nem jelezné**.
    """

    group_separators: list[str] = field(
        default_factory=lambda: list(_UNAMBIGUOUS_GROUP_SEPARATORS)
    )
    """Ezres-csoportosító karakterek, amiket eltávolítunk a szám előtt."""

    date_formats: list[str] = field(default_factory=lambda: [_ISO_DATE_FORMAT])
    """Elfogadott dátum-alakok, sorrendben (a szabványkönyvtár minta-nyelvén).

    Az alapérték az ISO-8601 — az **nem** locale, hanem szabvány, és
    egyértelmű. Minden más alak (`nap/hónap/év` vs. `hónap/nap/év`) kétértelmű,
    ezért csak kimondott konfigurációval fogadjuk el.
    """

    true_values: list[str] = field(default_factory=lambda: ["true"])
    false_values: list[str] = field(default_factory=lambda: ["false"])
    """Logikai értékek szöveges alakjai.

    Az alapérték az adat-csere konvenciója (`true`/`false`), nem természetes
    nyelv — így nem hordoz nyelvet, de a leggyakoribb gépi export működik.
    """

    def validate(self) -> None:
        """Fail-fast: az értelmetlen beállítás induláskor bukjon el.

        Ha egy hibás beállítás csak feldolgozás közben derül ki, akkor a hibát
        ott látjuk, ahol a hatása van, nem ott, ahol az oka.
        """
        if self.header_row < 1:
            raise ConfigurationError(
                f"A `header_row` 1-alapú sorszám, {self.header_row!r} nem lehet."
            )
        if self.data_starts_after_header < 0:
            raise ConfigurationError(
                "A `data_starts_after_header` nem lehet negatív."
            )
        if self.max_rows < 0:
            raise ConfigurationError("A `max_rows` nem lehet negatív (0 = nincs korlát).")
        if len(self.delimiter) > 1:
            raise ConfigurationError(
                f"Az elválasztó egyetlen karakter lehet, {self.delimiter!r} nem az."
            )
        if not self.encoding_candidates:
            raise ConfigurationError(
                "Legalább egy kódolás-jelölt kell, különben egy fájl sem olvasható."
            )
        if not self.delimiter and not self.delimiter_candidates:
            raise ConfigurationError(
                "Nincs megadott elválasztó, és a jelöltek listája is üres — "
                "így egyetlen fájl elválasztója sem lenne felismerhető."
            )
        for candidate in self.delimiter_candidates:
            if len(candidate) != 1:
                raise ConfigurationError(
                    f"Az elválasztó-jelölt egyetlen karakter lehet, {candidate!r} nem az."
                )
            if candidate.isspace() and candidate != "\t":
                raise ConfigurationError(
                    f"A(z) {candidate!r} térköz nem lehet elválasztó-jelölt: egy "
                    f"szöveges mezőben mindig van szóköz, tehát a felismerés "
                    f"csendben szavakra tördelné a sorokat. (A tabulátor kivétel.)"
                )
        for pair in self.unit_bracket_pairs:
            if len(pair) != 2:
                raise ConfigurationError(
                    f"A zárójel-pár nyitó+záró karakter, {pair!r} nem az."
                )
        if self.decimal_separator and len(self.decimal_separator) != 1:
            raise ConfigurationError(
                f"A tizedesjel egyetlen karakter lehet, {self.decimal_separator!r} nem az."
            )
        if self.decimal_separator and self.decimal_separator in self.group_separators:
            raise ConfigurationError(
                f"A tizedesjel ({self.decimal_separator!r}) nem lehet egyben "
                f"csoport-jel is — minden szám kétértelmű lenne."
            )
        overlap = set(self.true_values) & set(self.false_values)
        if overlap:
            raise ConfigurationError(
                f"Ugyanaz az érték igaznak ÉS hamisnak is számít: {sorted(overlap)}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TabularOptions":
        """Ismeretlen kulcsokat eldob (régebbi beállítás-fájlok miatt)."""
        known = cls.__dataclass_fields__.keys()
        options = cls(**{key: value for key, value in data.items() if key in known})
        options.validate()
        return options
