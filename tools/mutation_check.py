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

# A vizsgalt repo gyokere. Alapertelmezes: az eszkoz sajat repoja -- de a
# `--root` felulirja, hogy MAS repobol is futtathato legyen (a semlegessegi
# kapu ugyanezt teszi). Enelkul a ket repo ket MASOLATOT tartana ugyanabbol
# az eszkozbol, es a ket masolat elobb-utobb elternek.
REPO = Path(__file__).resolve().parent.parent

# A futtato ALAPERTELMEZESE: a Python motor sajat suite-ja. A `mutations.json`
# `runner` szakasza felulirhatja -- igy UGYANEZ az implementacio szolgalja ki a
# .NET modul-repot is (`dotnet test`), es nem keletkezik ket igazsag ugyanarrol a
# mechanizmusrol. Ugyanaz az elv, mint a semlegessegi kapunal: EGY implementacio,
# tobb szabalyhalmaz.
_DEFAULT_RUNNER = {
    "command": ["{python}", "-m", "unittest", "{test}"],
    "env": {"PYTHONPATH": "src"},
}


def run_test(target: str, runner: dict) -> bool:
    """Igaz, ha a megadott teszt-cel ZÖLD.

    A `{test}` helyettesitő a bejegyzes `test` mezojere cserelodik, a `{python}`
    az eppen futo ertelmezore. Mas helyettesitőt SZANDEKOSAN nem tamogatunk: egy
    szabad sablon-nyelv itt azt jelentene, hogy a mutacios eszkoz barmit
    futtathat, amit egy config-fajl kér — es ez a fajl a repoban all.
    """
    command = [
        part.replace("{python}", sys.executable).replace("{test}", target)
        for part in runner["command"]
    ]
    proc = subprocess.run(
        command,
        cwd=REPO,
        env={**os.environ, **runner.get("env", {})},
        capture_output=True,
    )
    return proc.returncode == 0


def apply_mutation(entry: dict, runner: dict) -> tuple[str, str]:
    """Visszaadja: (állapot, indoklás). Az állapot: FOG / NEM FOG / ERVENYTELEN."""
    if entry.get("kind") == "create":
        return _apply_create(entry, runner)
    return _apply_replace(entry, runner)


def _apply_create(entry: dict, runner: dict) -> tuple[str, str]:
    """FÁJL-LÉTREHOZÁSSAL mutál — mert néhány kapu csak így mutálható.

    ⚠ **Ezt egy hamis állításom hozta létre.** Egy ADR-ben azt írtam, hogy a
    modell-határ nyolc kapuja „mind mutációval igazolva" — aztán megszámoltam, és
    **négy** volt. A hiányzók közül az egyik (*„nincs számla-specifikus use-case"*)
    egy `pkgutil`-alapú kapu: **fájl-listát** vizsgál, tehát szöveg-cserével nem
    lehet elrontani. A gyengébb válasz az lett volna, hogy az állítást gyengítem;
    a helyes az, hogy az eszközt bővítem — különben egy egész kapu-fajta
    (*„nincs ilyen fájl"*) mérhetetlen marad.

    A visszaállítás a fájl **törlése**, `finally`-ben: egy megszakítás se hagyjon
    ott becsempészett modult.
    """
    path = REPO / entry["file"]
    if path.exists():
        return "ERVENYTELEN", f"a letrehozando fajl MAR letezik: {entry['file']}"

    if not run_test(entry["test"], runner):
        return "ERVENYTELEN", f"az alapallapot mar piros: {entry['test']}"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(entry["content"].encode("utf-8"))
    try:
        failed = not run_test(entry["test"], runner)
    finally:
        path.unlink(missing_ok=True)
        # A `__pycache__` a becsempeszett modulrol is keszul; ha ott marad, egy
        # kesobbi futas MEG IMPORTALHATJA -- es a kovetkezo meres ertelmezhetetlen
        # lenne. Nem elmeleti: a `pkgutil` a .pyc-t is modulnak latja.
        for cache in path.parent.glob("__pycache__/" + path.stem + ".*"):
            cache.unlink(missing_ok=True)

    return ("FOG", "a kapu elbuktatta a becsempeszett fajlt") if failed else (
        "NEM FOG",
        "a becsempeszett fajl ATMENT — a kapu ezt NEM meri",
    )


def _apply_replace(entry: dict, runner: dict) -> tuple[str, str]:
    """Szöveg-cserés mutáció (az alapeset)."""
    path = REPO / entry["file"]
    if not path.is_file():
        return "ERVENYTELEN", f"a fajl nem letezik: {entry['file']}"

    # ⚠ AZ ILLESZTES SZOVEGEN, A VISSZAALLITAS BAJTON — es ez a szetvalasztas
    # ket kulon, MEGTORTENT hiba kovetkezmenye:
    #
    # 1. Eloszor `read_text`/`write_text` part hasznaltunk. Windowson az
    #    `\n` -> `\r\n`-t fordit, tehat a visszaallitas szoveg-azonos volt, de NEM
    #    bajt-azonos -- es ez egy vendorolt, HASH-PINNELT szerzodes-fajlt elrontott.
    #    A pin-kapu fogta meg.
    # 2. Ezert bajt-szintre valtottunk -- amitol harom tobbsoros mutacios pont
    #    ERVENYTELEN lett: a keszletben LF all, a forrasfajlokban CRLF, tehat a
    #    bajt-illesztes nem talalt. A mutacio-keszlet igy CSENDBEN szukult volna,
    #    ha az eszkoz nem mondana ki az ERVENYTELEN meresset.
    #
    # A helyes valasz mindkettore: sorveg-fuggetlenul illesztunk (szoveg,
    # normalizalt sorvegekkel), de a visszaallitashoz az EREDETI BAJTOKAT tartjuk
    # meg. A mutalt allapot sorvegei nem erdekesek -- az atmeneti.
    original_bytes = path.read_bytes()
    text = original_bytes.decode("utf-8").replace("\r\n", "\n")

    if entry["find"] not in text:
        # NEM "sikeres": ha a mutacios pont elmozdult (atirtuk a kodot), a meres
        # semmit nem allit. Ez a leggyakoribb csendes hiba egy mutacios keszletben.
        return "ERVENYTELEN", "a mutacios pont nem talalhato (elmozdult a kod?)"

    if not run_test(entry["test"], runner):
        return "ERVENYTELEN", f"az alapallapot mar piros: {entry['test']}"

    path.write_bytes(text.replace(entry["find"], entry["replace"], 1).encode("utf-8"))
    try:
        failed = not run_test(entry["test"], runner)
    finally:
        # `finally`, hogy egy megszakitas (Ctrl-C, timeout) se hagyjon mutalt kodot.
        # `write_bytes` az EREDETI bajtokkal: a visszaallitas bajtra azonos.
        path.write_bytes(original_bytes)

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
    parser.add_argument("--root", default="", help="a vizsgalt repo gyokere")
    args = parser.parse_args()

    global REPO
    if args.root:
        REPO = Path(args.root).resolve()
        if not REPO.is_dir():
            print(f"HIBA: a megadott gyoker nem letezik: {args.root}")
            return 1

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    runner = config.get("runner", _DEFAULT_RUNNER)
    entries = config["mutations"]
    if args.only:
        entries = [e for e in entries if args.only in e["name"]]
    if not entries:
        print("Nincs futtathato mutacio — a meres vakon zold lenne.")
        return 1

    bites = invalid = 0
    print(f"Mutacios ellenorzo: {len(entries)} mutacio\n")
    for entry in entries:
        state, reason = apply_mutation(entry, runner)
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
