"""A motor konfigurációja — MINDEN beállítható érték egy helyen.

Miért ilyen szigorú: a prototípusok egy-egy konkrét cég konkrét rendszerére
készültek, és ami ott beégetett érték volt, az itt kivétel nélkül konfiguráció.
Ha bármelyik visszakerül a kódba, a termék egyetlen ügyfélnél használható.

HÁROM DOLOG, AMIT A FORRÁS-PROTOTÍPUSBÓL SZÁNDÉKOSAN MÁSKÉNT CSINÁLUNK
----------------------------------------------------------------------
1. **A mag nem ismeri az adaptereket.** A prototípus configjában gyártó-nevű
   kulcsok álltak (felismerő-motorok, vektortár, modell-szolgáltató paraméterei).
   Ettől a domain *tudott* az infrastruktúráról. Itt minden ilyen az
   `adapter_options` alá megy, amit a mag **nem értelmez** — csak továbbad.

2. **Titok soha nem kerül a configba.** A prototípus configjában volt egy
   kulcs-mező, és a config `save()`-elte magát JSON-ba — vagyis a titok
   lemezre íródott. Itt csak a környezeti változó NEVE tárolható
   (`credential_env`), az ÉRTÉKE soha. Ezt teszt is őrzi.

3. **Nincs beégetett ország, nyelv vagy pénznem.** Az üres alapérték azt
   jelenti: „az adapter döntse el", nem azt, hogy „magyar".

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from doccapture.core.errors import ConfigurationError
from doccapture.core.models import InputKind
from doccapture.core.tabular.options import TabularOptions
from doccapture.core.text_layer_options import TextLayerOptions

# Mezonevek, amik titkot sejtetnek. Nem a teljesseg a cel, hanem hogy a
# leggyakoribb elirast (`api_key` a configba) gepi kapu fogja meg, ne review.
_SECRET_HINTS = ("key", "secret", "token", "password", "credential")

# Kivetel: ez a mezo SZANDEKOSAN tartalmazza a "credential" szot, de csak
# valtozo-NEVEKET tarol, ertekeket nem. A megkulonboztetes lenyege az egesz
# mintanak: valtozo-hivatkozas != literal titok.
_CREDENTIAL_NAME_FIELD = "credential_env"


def _default_extension_routing() -> dict[str, InputKind]:
    """Kiterjesztés → a bemenet FELTÉTELEZETT útja.

    Egy helyen definiálva (a prototípus egyik jó szokása), de itt már a négy
    úthoz kötve — mert a négy bemenet négy külön út.

    ⚠ A `.pdf` szándékosan `TEXT_LAYER_DOCUMENT`: ez csak JELÖLT. A kiterjesztés
    nem tudja megmondani, van-e szövegréteg — azt meg kell nézni. Ha nincs, a
    fázis `RASTER_SCAN`-re vált. Ha ezt kiterjesztés alapján döntenénk el, a
    legolcsóbb esetet oldanánk meg a legdrágább úton (vagy fordítva).
    """
    return {
        ".csv": InputKind.TABULAR,
        ".xlsx": InputKind.TABULAR,
        ".xlsm": InputKind.TABULAR,
        ".pdf": InputKind.TEXT_LAYER_DOCUMENT,
        ".jpg": InputKind.RASTER_SCAN,
        ".jpeg": InputKind.RASTER_SCAN,
        ".png": InputKind.RASTER_SCAN,
        ".tif": InputKind.RASTER_SCAN,
        ".tiff": InputKind.RASTER_SCAN,
        ".bmp": InputKind.RASTER_SCAN,
        ".webp": InputKind.RASTER_SCAN,
    }


def _default_excluded_patterns() -> list[str]:
    """Zaj-fájlok, amiket ki kell hagyni.

    Minden éles mappában van biztonsági másolat, lock- és gyorsítótár-fájl.
    A lista KONFIGURÁCIÓ, mert rendszerenként más — de az alapértelmezés
    fedje a leggyakoribbakat, különben minden bevezetés ugyanazzal kezdődik.
    """
    return ["~$*", "*.bak", "*.tmp", ".~lock.*", "Thumbs.db", ".DS_Store"]


@dataclass
class CaptureConfig:
    """A motor minden beállítható értéke."""

    # --- Forrás ---
    input_root: str = "."
    """A bemeneti gyökér. Minden bizonyíték-útvonal EHHEZ képest relatív."""

    read_only_source: bool = True
    """A forrásmappa csak olvasható: nincs létrehozás, átnevezés, törlés, másolás.

    Alapértelmezésben igaz, és nem is javasolt hamisra állítani: az eredetit
    nem bántjuk, a normalizálás mindig másolaton dolgozik.
    """

    extension_routing: dict[str, InputKind] = field(
        default_factory=_default_extension_routing
    )

    excluded_name_patterns: list[str] = field(
        default_factory=_default_excluded_patterns
    )

    run_active_content: bool = False
    """Makró, képlet, lekérdezés, külső hivatkozás futtatása.

    Alapértelmezésben KIKAPCSOLVA, és ez nemcsak biztonsági kérdés:
    egy futtatott képlet ma és holnap mást adhat, tehát a determinizmus is
    elveszne. Aktív tartalmú fájlnál a tárolt gyorsítótárat olvassuk.
    """

    # --- Mértékegység ---
    preserve_original_units: bool = True
    """Amíg nem tudjuk biztosan az eredeti mértékegységet, ne normalizáljunk.

    A konverzió explicit és naplózott — soha nem néma.
    """

    # --- Adatvédelem: hol futhat a modellt igénylő fázis (G4) ---
    allow_external_processing: bool = False
    """Elhagyhatja-e a forrás a telepítést egy külső szolgáltató felé.

    **G4-döntés (Gábor, 2026-07-30): helyi alap, külső opcionális.** Ezért az
    alapérték `False`: a biztonságos viselkedés az alapértelmezés, a külső
    feldolgozás a **kimondott** kivétel. Ha ez fordítva lenne, egy elfelejtett
    beállítás miatt ügyfél-számlák mennének ki egy külső szolgáltatóhoz — és
    semmi nem jelezné.

    Ez nem korlát, hanem **eladási érv**: egy „az adatai nem hagyják el a
    telephelyet" változat más piacot nyit, és itt a különbség konfiguráció.
    """

    external_processing_audit_note: str = ""
    """Miért van engedve a külső feldolgozás — ki, mikor és milyen alapon döntött.

    Kötelező, ha `allow_external_processing` igaz. Miért: egy `true` értékű
    kapcsoló fél év múlva megmagyarázhatatlan, és senki nem meri visszavenni.
    Ez a mező teszi a döntést **visszakereshetővé** — nem titkot tárol, hanem
    indokot.
    """

    # --- Táblázatos út ---
    tabular: TabularOptions = field(default_factory=TabularOptions)
    """A táblázatos bemenet olvasási módja (fejléc-sor, elválasztó, számformátum).

    Beágyazott csomag és nem húsz lapos mező: ezek együtt alkotnak egy értelmes
    egészt, és laposan szétszórva nem látszana, melyik melyikkel függ össze.
    """

    # --- Szövegréteges út ---
    text_layer: TextLayerOptions = field(default_factory=TextLayerOptions)
    """A szövegréteg használhatóságának küszöbei (mikor megyünk ezen az úton).

    Ugyanaz a minta, mint a `tabular`: beágyazott csomag, mert ezek együtt
    alkotnak egy döntést — és a `validate()` rekurzívan végigkérdezi.
    """

    # --- Bizonytalanság kezelése ---
    human_only_field_types: list[str] = field(default_factory=list)
    """Mezőtípusok, amiket NEM olvasunk gépileg, hanem emberi kitöltésre jelölünk.

    Ha egy mezőtípusnál a gépi olvasás tudottan megbízhatatlan (hosszú
    azonosító-számok, kézírás), akkor jobb kimondottan hiányt adni, mint
    magabiztosan rossz értéket. Mezőtípusonként konfigurálható — nem beégetett
    tiltás, mert rendszerenként más a megbízhatatlan mező.
    """

    redundancy_tolerance: float = 0.01
    """Tűrés az önellenőrző számtannál (pl. mennyiség × egységár = tétel-érték).

    Ha a redundáns értékek ezen felül térnek el: JELÖLÜNK, nem javítunk csendben.
    """

    # --- Végrehajtás ---
    retry_attempts: int = 4
    retry_backoff_factor: float = 2.0
    request_timeout_seconds: int = 120
    max_concurrent_tasks: int = 8

    # --- Adapterek ---
    adapter_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    """Adapter-specifikus beállítások, adapter-név → szabad kulcs-érték.

    A mag ezt NEM értelmezi, csak továbbadja. Így a domain nem tud arról, hogy
    éppen melyik felismerő vagy melyik tár van mögötte — és az adapter
    cserélhető anélkül, hogy a mag változna.
    """

    credential_env: dict[str, str] = field(default_factory=dict)
    """Adapter-név → a titkot tartalmazó KÖRNYEZETI VÁLTOZÓ NEVE.

    Itt soha nem áll titok, csak a neve. A hitelesítő értéke a környezetből
    vagy a szolgáltatás-kezelőből jön, és nem kerül sem configba, sem repóba.
    """

    # ------------------------------------------------------------------
    # Szerializálás — a fájlba írás/olvasás NEM itt van (ld. `from_dict`)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Szerializálható alak — és közben megvédi magát a titok-szivárgástól."""
        self.assert_no_secret_values()
        data = asdict(self)
        # Az Enum ertekeket kiirhato alakra hozzuk.
        data["extension_routing"] = {
            ext: kind.value for ext, kind in self.extension_routing.items()
        }
        return data

    def validate(self) -> None:
        """Az egész config ellentmondás-mentessége. Fail-fast, induláskor.

        A beágyazott beállításokat is végigkérdezi: ha csak a legfelső szintet
        ellenőriznénk, egy hibás táblázat-beállítás feldolgozás közben bukna el,
        vagyis ott, ahol a hatása van, nem ott, ahol az oka.
        """
        self.assert_no_secret_values()
        self.tabular.validate()
        self.text_layer.validate()

        if self.allow_external_processing and not self.external_processing_audit_note.strip():
            raise ConfigurationError(
                "A külső feldolgozás engedve van, de nincs megadva indok "
                "(`external_processing_audit_note`). Egy indoklás nélküli "
                "engedély fél év múlva megmagyarázhatatlan, és senki nem meri "
                "visszavenni — ezért kötelező."
            )
        if self.redundancy_tolerance < 0:
            raise ConfigurationError("A redundancia-tűrés nem lehet negatív.")

    def assert_external_processing_allowed(self, adapter_name: str) -> None:
        """A G4-kapu: elbukik, ha a forrás nem hagyhatja el a telepítést.

        Minden adapternek meg kell hívnia, ami a forrást kiengedi — és ezt
        **nem** a jóindulat garantálja: az adapter-teszteknek mérni kell, hogy
        a kapu nélkül nem indul el a hívás.

        Fail-closed: az alapállapot a tiltás, tehát egy elfelejtett beállítás
        nem szivárgáshoz vezet, hanem kimondott hibához.
        """
        if not self.allow_external_processing:
            raise ConfigurationError(
                f"A(z) {adapter_name!r} adapter a forrást kiengedné a telepítésből, "
                f"de a külső feldolgozás nincs engedve (G4). Ha ez szándékos, "
                f"állítsd `allow_external_processing=True`-ra, és add meg az "
                f"indokot az `external_processing_audit_note` mezőben."
            )
        if not self.external_processing_audit_note.strip():
            raise ConfigurationError(
                f"A(z) {adapter_name!r} adapter külső feldolgozást kérne, és az "
                f"engedve van — de nincs indok. A határátlépés legyen "
                f"visszakereshető."
            )

    def assert_no_secret_values(self) -> None:
        """Elbukik, ha titkot sejtető mezőbe ÉRTÉK került.

        Miért kapu és nem konvenció: a legdrágább hibák nem attól lettek
        drágák, hogy senki nem tudta a szabályt, hanem hogy senki nem mérte.
        """
        # `vars(self)` es nem `asdict(self)`: az asdict CSAK a deklaralt mezoket
        # adja vissza, tehat egy kesobb hozzaadott `api_key`-t nem is latna --
        # a kapu pont attol lenne vak, ami ellen vedeni akar.
        for name, value in vars(self).items():
            if name == _CREDENTIAL_NAME_FIELD:
                continue
            if not any(hint in name.lower() for hint in _SECRET_HINTS):
                continue
            if value:
                raise ConfigurationError(
                    f"A(z) {name!r} mező titkot sejtet, és értéket tartalmaz. "
                    f"A configba a titok NEVE kerül (credential_env), az ÉRTÉKE soha — "
                    f"az érték a környezetből jöjjön."
                )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CaptureConfig":
        """Szótárból config — a szerializálás DOMAIN-tudása.

        ⚠ **Ez a metódus szándékosan nem nyit fájlt.** A perzisztálás (honnan
        jön a szótár) infrastruktúra: `infrastructure/config_store.py`. A
        határt gépi kapu méri (`tests/test_core_boundary.py`), és a szétválasztás
        pont ezt a metódust hagyja itt: **hogy** néz ki a szerializált alak, az
        a domain kérdése; **hol tároljuk**, az nem.

        Az ismeretlen kulcsokat eldobja (régebbi fájlok miatt), de a
        kiterjesztés-útvonalakat visszaalakítja `InputKind`-dá — mert egy
        elgépelt bemenet-fajta induláskor derüljön ki, ne feldolgozás közben.
        """
        known = cls.__dataclass_fields__.keys()
        filtered = {key: value for key, value in data.items() if key in known}

        # A BEAGYAZOTT dataclass visszaallitasa. Ez konnyen kimarad, es a hiba
        # NEM itt jelenik meg: a `cls(**filtered)` ilyenkor egy sima dict-et tesz
        # a `tabular` mezobe, es a hiba majd ott bukik ki, ahol valaki
        # `config.tabular.header_row`-t ir -- vagyis messze az okatol.
        tabular = filtered.get("tabular")
        if tabular is not None:
            if not isinstance(tabular, dict):
                raise ConfigurationError(
                    f"A `tabular` beállítás objektumot vár, nem {type(tabular).__name__}-t."
                )
            filtered["tabular"] = TabularOptions.from_dict(tabular)

        text_layer = filtered.get("text_layer")
        if text_layer is not None:
            if not isinstance(text_layer, dict):
                raise ConfigurationError(
                    f"A `text_layer` beállítás objektumot vár, nem {type(text_layer).__name__}-t."
                )
            filtered["text_layer"] = TextLayerOptions.from_dict(text_layer)

        routing = filtered.get("extension_routing")
        if routing is not None:
            try:
                filtered["extension_routing"] = {
                    ext: InputKind(kind) for ext, kind in routing.items()
                }
            except ValueError as exc:
                raise ConfigurationError(
                    f"Ismeretlen bemenet-fajta a kiterjesztes-utvonalakban: {exc}"
                ) from exc

        config = cls(**filtered)
        config.validate()
        return config
