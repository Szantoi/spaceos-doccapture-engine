"""Mutációs ellenőrző: bizonyítja, hogy a kapuk HARAPNAK.

MIÉRT REPO-ESZKÖZ, ÉS NEM ELDOBHATÓ SZKRIPT
-------------------------------------------
A QUALITY §5 kimondja: *„nem kell mindig LLM-nek generálnia a megoldást — az a
jó, ha paraméterezhető szkript készül, amit a változásoknál újra fel lehet
használni."* Ez a mérés minden szeletben kell, és ha eldobható mappában él,
a következő körben **újra meg kell írni** — vagyis a mérés minden alkalommal
más lesz, és nem lesz összehasonlítható.

MIT BIZONYÍT, ÉS MIT NEM — EZT KI KELL MONDANI
----------------------------------------------
A mutáció az **érzékenységet** bizonyítja: azt, hogy a kapu fog azon, amit
**megnéz**. **NEM** bizonyítja a lefedettséget — arról, hogy mit *nem* néz meg,
ez az eszköz semmit nem mond. Ezért a kimenet **arányt** ír ki (`X/Y`), és a
`mutations.json`-ban minden mutáció mellett ott áll, hogy **mit állít**.

HOGYAN MŰKÖDIK
--------------
Minden mutációnál:

1. **alapállapot-ellenőrzés** — a teszt zöld-e mutáció nélkül. Ha nem, a mutáció
   értelmezhetetlen (nem tudnánk, mi buktatta el), és ezt **kimondjuk**;
2. a mutációs pont megléte — ha a keresett szöveg nincs meg, a mérés
   **érvénytelen**, nem „sikeres";
3. a mutáció alkalmazása, a teszt futtatása, majd a fájl **visszaállítása**
   `finally`-ben — hogy egy megszakítás se hagyjon mutált kódot a fán.

Használat:
    python tools/mutation_check.py                      # tools/mutations.json
    python tools/mutation_check.py --config sajat.json
    python tools/mutation_check.py --only hatar-kapu    # egy mutáció szűrve
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_test(target: str) -> bool:
    """Igaz, ha a megadott teszt-modul ZÖLD."""
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", target],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": "src"},
        capture_output=True,
    )
    return proc.returncode == 0


def apply_mutation(entry: dict) -> tuple[str, str]:
    """Visszaadja: (állapot, indoklás). Az állapot: FOG / NEM FOG / ERVENYTELEN."""
    path = REPO / entry["file"]
    if not path.is_file():
        return "ERVENYTELEN", f"a fajl nem letezik: {entry['file']}"

    original = path.read_text(encoding="utf-8")
    if entry["find"] not in original:
        # NEM "sikeres": ha a mutacios pont elmozdult (atirtuk a kodot), a meres
        # semmit nem allit. Ez a leggyakoribb csendes hiba egy mutacios keszletben.
        return "ERVENYTELEN", "a mutacios pont nem talalhato (elmozdult a kod?)"

    if not run_test(entry["test"]):
        return "ERVENYTELEN", f"az alapallapot mar piros: {entry['test']}"

    path.write_text(original.replace(entry["find"], entry["replace"], 1), encoding="utf-8")
    try:
        failed = not run_test(entry["test"])
    finally:
        # `finally`, hogy egy megszakitas (Ctrl-C, timeout) se hagyjon mutalt kodot.
        path.write_text(original, encoding="utf-8")

    return ("FOG", "a kapu elbuktatta a mutaciot") if failed else (
        "NEM FOG",
        "a mutacio ATMENT — a kapu ezt a viselkedest NEM meri",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Mutacios ellenorzo")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("mutations.json")),
        help="a mutacio-keszlet leiroja",
    )
    parser.add_argument("--only", default="", help="csak az ezt a szoveget tartalmazo mutaciok")
    args = parser.parse_args()

    entries = json.loads(Path(args.config).read_text(encoding="utf-8"))["mutations"]
    if args.only:
        entries = [e for e in entries if args.only in e["name"]]
    if not entries:
        print("Nincs futtathato mutacio — a meres vakon zold lenne.")
        return 1

    bites = invalid = 0
    print(f"Mutacios ellenorzo: {len(entries)} mutacio\n")
    for entry in entries:
        state, reason = apply_mutation(entry)
        bites += state == "FOG"
        invalid += state == "ERVENYTELEN"
        print(f"  [{state:12}] {entry['name']}")
        print(f"                 allitas: {entry['asserts']}")
        if state != "FOG":
            print(f"                 ⚠ {reason}")

    measured = len(entries) - invalid
    print(f"\nMUTACIO: {bites}/{measured} kapu bizonyitottan harap", end="")
    print(f"  (+{invalid} ERVENYTELEN meres)" if invalid else "")
    print(
        "\n⚠ A mutacio az ERZEKENYSEGET bizonyitja, nem a lefedettseget: azt "
        "allitja, hogy\n   a kapu fog azon, amit MEGNEZ. Amit nem nez meg, arrol "
        "ez az eszkoz semmit\n   nem mond — a `mutations.json` `not_covered` "
        "szakasza nevezi meg azokat."
    )
    return 0 if (bites == measured and invalid == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
