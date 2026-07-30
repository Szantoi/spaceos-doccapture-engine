"""A kontraktus hash-pinje: kiszámítás és ellenőrzés.

MIT HASHELÜNK — KIMONDVA
------------------------
Nem „a kontraktus hashe", hanem a **`contracts/capture-record.schema.json` fájl
bájtjainak** SHA-256-ja. Ezt ki kell mondani, mert egy hash önmagában nem
azonosít semmit: ugyanaz a hash két helyen két külön leletnek látszik, ha nem
tudjuk, **mi** volt a bemenete.

MIÉRT BÁJT-SZINTŰ, ÉS MIÉRT SZÁNDÉKOS
-------------------------------------
Egy pusztán formázási változás (behúzás, kulcs-sorrend) is **új pint** ad. Ez
nem hiba, hanem döntés: a **hamis nyugalom rosszabb**, mint egy fölösleges
pin-frissítés. Ha a hash „szemantikus" lenne, el kellene dönteni, mi a
szemantika — és minden ilyen döntés egy rés, amin egy valódi változás átcsúszik.

MIÉRT KÜLÖN FÁJL A PIN
----------------------
Ha a hash a sémában lenne, önmagát kellene hashelnie. A külön fájl teszi
lehetővé, hogy a fogyasztó **a séma mellé** vendorolja a pint, és a kettő
egyezését build-időben ellenőrizze.

Használat:
    python tools/contract_pin.py            # ellenorzes (CI-ben ez fut)
    python tools/contract_pin.py --write    # ujraszamitas es kiiras
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "contracts" / "capture-record.schema.json"
PIN = REPO / "contracts" / "capture-record.pin.json"

HASH_ALGORITHM = "sha256"
HASHED_INPUT = "a contracts/capture-record.schema.json fajl bajtjai"
"""**Kimondva, mit hasheltunk.** Ez a szoveg a pin-fajlba is bekerul: enelkul egy
kesobbi ellenorzo nem tudja, mit kellene ujraszamolnia."""


def schema_digest() -> str:
    raw = SCHEMA.read_bytes()
    return f"{HASH_ALGORITHM}:{hashlib.new(HASH_ALGORITHM, raw).hexdigest()}"


def contract_version() -> str:
    """A verzió a SÉMÁBÓL, nem külön beírva.

    Ha két helyen állna, az egyik előbb-utóbb elcsúszna — és épp a
    verzió-egyezésen múlik, hogy a fogyasztó felismeri-e a törő változást.
    A séma `$id`-je hordozza: `…/capture-record/<verzio>`.
    """
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    identifier = str(schema.get("$id", ""))
    version = identifier.rstrip("/").rsplit("/", 1)[-1]
    if not version or not all(part.isdigit() for part in version.split(".")):
        raise SystemExit(
            f"A sema $id-jebol nem olvashato ki verzio: {identifier!r}. "
            f"Elvart alak: .../capture-record/<major>.<minor>.<patch>"
        )
    return version


def write_pin() -> dict[str, str]:
    payload = {
        "_comment": [
            "A publikalt Capture-kontraktus hash-pinje. GENERALT fajl:",
            "`python tools/contract_pin.py --write`.",
            "",
            "A 'hashed_input' NEM diszites: egy hash onmagaban nem azonosit semmit,",
            "ha nem tudjuk, mi volt a bemenete. Enelkul egy kesobbi ellenorzo nem",
            "tudja, mit kellene ujraszamolnia.",
        ],
        "contract_version": contract_version(),
        "schema_file": SCHEMA.name,
        "hashed_input": HASHED_INPUT,
        "digest": schema_digest(),
    }
    # `newline=""`: a `write_text` alapertelmezesben a PLATFORM sorveget hasznalja,
    # tehat Windowson CRLF-et irna. Egy szerzodes-muveltarnal ez lappango csapda:
    # a fajl platformonkent mas bajtokat kap, es ha valaha hasheles ala esik, a pin
    # PLATFORM-FUGGO lesz. Ezt a `tests/test_contract.LineEndingTests` kapuja fogta
    # meg -- es ugyanez a hiba a vendorolt masolatot mar egyszer el is rontotta.
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    PIN.write_text(body, encoding="utf-8", newline="")
    return payload


def verify_pin() -> int:
    if not PIN.is_file():
        print(f"HIBA: a pin-fajl nem letezik ({PIN.name}). Futtasd: --write")
        return 1

    pin = json.loads(PIN.read_text(encoding="utf-8"))
    problems: list[str] = []

    expected = schema_digest()
    if pin.get("digest") != expected:
        problems.append(
            f"a sema hashe elcsuszott\n"
            f"    pinben : {pin.get('digest')}\n"
            f"    mert   : {expected}\n"
            f"    hashelt bemenet: {HASHED_INPUT}"
        )

    version = contract_version()
    if pin.get("contract_version") != version:
        problems.append(
            f"a verzio elcsuszott: pinben {pin.get('contract_version')!r}, "
            f"a sema $id-jeben {version!r}"
        )

    # A wire-szerializalo verzioja is EGYEZZEN: harom helyen allo verzio harom
    # igazsag lenne, es a fogyaszto epp a verzio alapjan ismeri fel a toro valtozast.
    sys.path.insert(0, str(REPO / "src"))
    from doccapture.infrastructure.wire import CONTRACT_VERSION  # noqa: PLC0415

    if CONTRACT_VERSION != version:
        problems.append(
            f"a szerializalo verzioja ({CONTRACT_VERSION!r}) nem egyezik a sema "
            f"$id-jeben allo verzioval ({version!r})"
        )

    if pin.get("hashed_input") != HASHED_INPUT:
        problems.append(
            "a pin nem mondja meg, mit hasheltunk (a 'hashed_input' elcsuszott) — "
            "enelkul a hash nem azonosit semmit"
        )

    if problems:
        print("Kontraktus-pin: ELCSUSZOTT\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nHa a valtozas SZANDEKOS: emeld a verziot a sema $id-jeben ES a\n"
            "wire.py CONTRACT_VERSION-jeben, majd futtasd: "
            "python tools/contract_pin.py --write\n"
            "A verzio-emeles KIMONDOTT lepes, nem mellekhatas."
        )
        return 1

    print(f"Kontraktus-pin: EGYEZIK  (verzio {version}, {expected[:19]}…)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="A Capture-kontraktus hash-pinje")
    parser.add_argument("--write", action="store_true", help="ujraszamitas es kiiras")
    args = parser.parse_args()

    if not SCHEMA.is_file():
        print(f"HIBA: a sema nem letezik: {SCHEMA}")
        return 1

    if args.write:
        payload = write_pin()
        print(f"Pin kiirva: verzio {payload['contract_version']}, {payload['digest'][:19]}…")
        return 0

    return verify_pin()


if __name__ == "__main__":
    raise SystemExit(main())
