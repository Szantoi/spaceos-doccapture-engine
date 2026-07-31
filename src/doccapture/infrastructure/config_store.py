"""A konfiguráció perzisztálása — fájlba írás és olvasás.

MIÉRT NEM A MAGBAN (és miért került ide utólag)
-----------------------------------------------
A `CaptureConfig` sokáig maga mentette és töltötte magát (`save`/`load`), és ez
**csendben** sértette a hexagonális határt: a domain-objektum fájlt nyitott.
Nem elméleti kifogás — az akkori határ-kapu **csak importokat** vizsgált, az
`open()` pedig beépített függvény, a `pathlib` pedig szabványkönyvtár, tehát a
sértés **átment rajta**.

A DC-01a-ban a kaput kiterjesztettük fájlrendszer-hozzáférésre, és az **azonnal
megfogta ezt a meglévő sértést**. A választás nem az volt, hogy „kivétel vagy
javítás": egyetlen sértés kedvéért kivétel-listát nyitni azt üzenné, hogy a kapu
alkuképes — a következő kivételt már senki nem vitatná meg.

A szétválasztás vonala:

| Kérdés | Hol dől el | Miért |
|---|---|---|
| **Hogyan** néz ki a szerializált alak | mag (`to_dict`/`from_dict`) | ez domain-tudás: melyik mező mit jelent, mit kell `InputKind`-dá visszaalakítani |
| **Hová** kerül | itt | ez telepítési kérdés: fájl, adatbázis vagy titok-kezelő — a domaint nem érdekli |

Precedens ugyanebben a rétegben: `infrastructure/profile_registry.py` — a profil
**adat**, a betöltése infrastruktúra.
"""

from __future__ import annotations

import json
from pathlib import Path

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.observability import get_logger, log_step

_log = get_logger("config_store")


def save_config(config: CaptureConfig, file_path: str) -> None:
    """Kiírás JSON-ba. Titkot tartalmazó configot nem ír ki (fail-closed).

    ⚠ **A `to_dict()` SZÁNDÉKOSAN a fájl megnyitása ELŐTT fut**, mert az
    ellenőrzést (`assert_no_secret_values`) az tartalmazza. Az `open(..., "w")`
    ugyanis már létrehozza és **nullára csonkolja** a fájlt — ha az ellenőrzés
    utána bukna el, egy meglévő, helyes configot veszítenénk el a bukás
    **mellékhatásaként**. Ezt annak idején a saját tesztünk fogta meg, és a
    tesztje a mai napig méri (`test_titkot_tartalmazo_configot_nem_ir_ki`:
    a bukás után a fájl **nem is létezhet**).
    """
    payload = config.to_dict()
    with open(file_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    log_step(_log, "config.save", fields=len(payload))


def load_config(file_path: str) -> CaptureConfig:
    """Betöltés JSON-ból.

    ⚠ Az ellenőrzést **nem** itt hívjuk: a `CaptureConfig.from_dict()` már
    validál. Ha itt is meghívnánk, két helyen dőlne el ugyanaz — és két igazság
    ugyanarról előbb-utóbb elcsúszik (pl. valaki az egyiket kiveszi, a másikról
    megfeledkezik, és a hiányzó ellenőrzés csendben marad).
    """
    path = Path(file_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SourceUnreadableError(
            f"A konfiguráció nem olvasható: {path.name} ({exc})"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SourceUnreadableError(
            f"A konfiguráció nem értelmezhető JSON: {path.name} ({exc})"
        ) from exc

    config = CaptureConfig.from_dict(data)
    log_step(_log, "config.load", fields=len(data))
    return config
