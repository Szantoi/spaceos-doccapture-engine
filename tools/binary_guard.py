"""Bináris-kapu: mi kerülhet a repóba, és bizonyítottan az van-e ott.

MIÉRT LÉTEZIK — EGY MÉRT, TELJES HIÁNY
--------------------------------------
A repó **publikus**, és a saját szabályunk kimondja, hogy *üzleti bináris SOSEM
kerül be*. **Mérve viszont: ezt semmi nem őrizte.** A `.gitignore` néhány
konkrét kiterjesztést tilt (`*.pdf`, `*.xlsx`, `*.jpg`, `*.png`), de ez
**felsorolás, nem szabály** — egy `.ttf`, `.dll`, `.zip`, `.bin` vagy egy
átnevezett üzleti minta **csendben bemegy**.

⚠ **Ezt a hiányt egy saját, pontatlan állításom hozta elő:** azt jelentettem,
hogy „a `.gitignore` binárist tilt, tehát szűk kivétel kell". Megmérve **nem
tilt** — vagyis nem kivételt kellett adni egy tiltás alól, hanem **a hiányzó
kaput megépíteni**. A kettő ellentétes irányú munka, és a különbség csak
mérésből derült ki.

A MÁSODIK RÉS, AMIT UGYANEZ ZÁR BE
----------------------------------
A licenc-kapu (`tools/license_guard.py`, G5) **csak pip-csomagokat lát**. Egy
szállított **nem-pip** artefaktum — mint a beágyazott betűtípus — licenc-oldalon
**mérés nélkül** maradna: a `LICENSE` fájl ott lehet a repóban, és a G5-öt őrző
gépi kapu **akkor sem tud róla**. A manifeszt ezt zárja be: minden bináris
artefaktumnak van SPDX-azonosítója, licenc-fájlja és megnevezett eredete.

MIT MÉR — NÉGY KÜLÖN KÉRDÉS
---------------------------
1. **Engedélyezett-e?** Minden követett bináris fájl szerepel-e a manifesztben.
   Egy nem deklarált bináris **bukás**, nem figyelmeztetés.
2. **Az-e, aminek mondjuk?** A deklarált `sha256` egyezik-e a fájllal. Egy
   kicserélt betűtípus a terméket **némán** rontaná el (ld. lent).
3. **Megvan-e a licenc?** A deklarált licenc-fájl létezik, és a szövege
   tartalmazza a deklarált SPDX-azonosító jellemző nyomát.
4. **Használható-e a betűtípus?** A `.ttf`-eknél a kapu **megnyitja és megméri**:
   fedi-e a megkövetelt karakterkészletet, és engedi-e a beágyazást.

⚠ **A 4. pont nem formalitás.** Mérve, ugyanaz a hibás PDF két olvasóval három
különböző hibaalakot ad; a beépített Helvetica az egyik olvasón **helyes
hosszúságú** szöveget ad, csak a karakter `■`. Vagyis egy „nincs tiltott
karakter" vagy hossz-alapú ellenőrzés **üresen zöld**. És a hiba **láthatatlan
szövegrétegben** van, tehát szemmel soha nem derül ki. A fedést ezért **a
betűtípusból magából** kell megmérni, nem a kimenetből.

MIT NEM MÉR — KIMONDVA
----------------------
1. **A licenc jogi értelmezését nem.** SPDX-azonosítót és fájl-jelenlétet mér.
2. **A betűtípus vizuális minőségét nem** (hinting, kerning) — csak a glyph-fedést.
3. **A módosított származék átnevezési kötelezettségét nem** (OFL Reserved Font
   Name): ma nem módosítunk betűtípust, tehát nincs mit mérni. Ha valaha
   módosítunk, az **külön kaput** igényel.

Használat:
    python tools/binary_guard.py
    python tools/binary_guard.py --selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "tools" / "binary_artifacts.json"

# Amit binarisnak tekintunk: a fajl elso blokkjaban NUL-bajt van. Ez ugyanaz a
# heurisztika, amit a git hasznal -- es SZANDEKOSAN ugyanaz: a kapu arra a
# halmazra alljon, amit a verziokezelo is binarisnak lat.
_PROBE_BYTES = 8000

# A magyar keszlet KIEMELVE, mert a hosszu ekezet az, ami a beepitett
# betutipusoknal elesik -- es eppen ez a termek mai celnyelve.
#
# ⚠ Ez KONFIGURACIO, nem beegetett szabaly: mas nyelvteruletre mas keszlet kell,
# es a termek tobb nyelvteruleten el. A lista bovitese NEM kodvaltozas kerdese
# kell legyen, amint a masodik nyelvterulet megjelenik.
HUNGARIAN_CHARSET = "aábcdeéfghiíjklmnoóöőpqrstuúüűvwxyz"

# A MEGKOVETELT karakterkeszlet.
REQUIRED_CHARSET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789 .,:;-/()%"
    + HUNGARIAN_CHARSET
    + HUNGARIAN_CHARSET.upper()
)

# Amit a betutipusnak NEM kell tudnia -- a meres POZITIV kontrollja. Enelkul egy
# "minden karakter megvan" valaszt ado hibas olvaso is atmenne.
ABSENT_CONTROL = "中ア"  # CJK + katakana


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_binary(path: Path) -> bool:
    """A git heurisztikaja: NUL-bajt az elso blokkban.

    ⚠ A `with` nem stilus: enelkul a kapu MINDEN kovetett fajlra nyitva hagy egy
    leirot (`ResourceWarning`-gal jart, es a sajat suite-om jelezte). Egy
    szivargo mérőeszköz nagy repon eleri a leiro-korlatot, es akkor a kapu nem
    "piros" lesz, hanem ERTELMEZHETETLEN.
    """
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(_PROBE_BYTES)
    except OSError:
        return False


def tracked_files(root: Path) -> list[Path]:
    """A KOVETETT fajlok listaja.

    ⚠ Szandekosan `git ls-files`, nem `rglob`: a kapu arra a halmazra all, ami
    a repoval EGYUTT megy ki. Egy munkafaban heverő, kovetetlen binaris nem a mi
    dolgunk -- egy KOVETETT igen. (Ugyanaz a tanulsag, mint a gitignore-nal: a
    `git ls-files` a bizonyitek, nem a fajlrendszer.)
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [root / name.decode("utf-8") for name in proc.stdout.split(b"\x00") if name]


# ----------------------------------------------------------------------
# TrueType: a glyph-fedes merese, fuggoseg NELKUL
# ----------------------------------------------------------------------


def _tables(data: bytes) -> dict[str, tuple[int, int]]:
    count = struct.unpack(">H", data[4:6])[0]
    result: dict[str, tuple[int, int]] = {}
    for index in range(count):
        entry = 12 + index * 16
        tag = data[entry : entry + 4].decode("latin-1")
        offset, length = struct.unpack(">II", data[entry + 8 : entry + 16])
        result[tag] = (offset, length)
    return result


def _cmap_lookup(data: bytes, tables: dict[str, tuple[int, int]]):
    """A Unicode BMP `format 4` alábla — ezt használja minden mai olvasó."""
    base = tables["cmap"][0]
    count = struct.unpack(">H", data[base + 2 : base + 4])[0]
    chosen: int | None = None
    for index in range(count):
        entry = base + 4 + index * 8
        platform, encoding, sub_offset = struct.unpack(">HHI", data[entry : entry + 8])
        start = base + sub_offset
        if struct.unpack(">H", data[start : start + 2])[0] == 4 and (platform, encoding) in (
            (3, 1),
            (0, 3),
            (0, 4),
        ):
            chosen = start
    if chosen is None:
        raise ValueError("nincs Unicode BMP (format 4) cmap alabla")

    seg_x2 = struct.unpack(">H", data[chosen + 6 : chosen + 8])[0]
    segments = seg_x2 // 2
    ends = struct.unpack(f">{segments}H", data[chosen + 14 : chosen + 14 + seg_x2])
    starts = struct.unpack(
        f">{segments}H", data[chosen + 16 + seg_x2 : chosen + 16 + 2 * seg_x2]
    )
    deltas = struct.unpack(
        f">{segments}h", data[chosen + 16 + 2 * seg_x2 : chosen + 16 + 3 * seg_x2]
    )
    range_base = chosen + 16 + 3 * seg_x2
    range_offsets = struct.unpack(f">{segments}H", data[range_base : range_base + seg_x2])

    def glyph_for(char: str) -> int:
        code = ord(char)
        for index in range(segments):
            if starts[index] <= code <= ends[index]:
                if range_offsets[index] == 0:
                    return (code + deltas[index]) & 0xFFFF
                at = range_base + index * 2 + range_offsets[index] + (code - starts[index]) * 2
                glyph = struct.unpack(">H", data[at : at + 2])[0]
                return 0 if glyph == 0 else (glyph + deltas[index]) & 0xFFFF
        return 0

    return glyph_for


def font_report(path: Path, charset: str | None = None) -> dict:
    """A betűtípus mért jellemzői. `missing` üres = a készlet fedve van.

    ⚠ A `charset` alapertelmezese `None`, es a modul-konstans a TORZSBEN oldodik
    fel -- NEM `charset: str = REQUIRED_CHARSET`. Ezt egy bukó teszt hozta elo:
    a Python az alapertelmezett argumentumot a fuggveny DEFINICIOJAKOR koti be,
    tehat a konstans kesobbi valtoztatasa nem latszott volna. Egy „konfiguracio",
    amit valojaban nem lehet megvaltoztatni, rosszabb, mint egy beegetett ertek:
    azt hisszuk, hogy allitottunk rajta.
    """
    if charset is None:
        charset = REQUIRED_CHARSET
    data = path.read_bytes()
    tables = _tables(data)
    glyph_for = _cmap_lookup(data, tables)

    missing = sorted({char for char in charset if glyph_for(char) == 0})
    present_control = sorted({char for char in ABSENT_CONTROL if glyph_for(char) != 0})

    os2_offset = tables["OS/2"][0]
    fs_type = struct.unpack(">H", data[os2_offset + 8 : os2_offset + 10])[0]

    return {
        "missing": missing,
        "measured": len(set(charset)),
        "present_control": present_control,
        "fs_type": fs_type,
        # fsType bit 1 (ertek 2) = Restricted License Embedding -> beagyazas TILOS.
        "embeddable": not (fs_type & 0x0002),
    }


# ----------------------------------------------------------------------


def check(root: Path, manifest: dict) -> list[str]:
    problems: list[str] = []
    declared = {entry["path"]: entry for entry in manifest["artifacts"]}

    # 1) Engedelyezett-e minden KOVETETT binaris
    found: list[str] = []
    for path in tracked_files(root):
        if not path.is_file() or not is_binary(path):
            continue
        rel = path.relative_to(root).as_posix()
        found.append(rel)
        if rel not in declared:
            problems.append(
                f"NEM DEKLARALT binaris a repoban: {rel}. A repo PUBLIKUS -- "
                f"vedd fel a tools/binary_artifacts.json-ba (ut, sha256, licenc, "
                f"eredet), vagy tavolitsd el."
            )

    # 2) Az-e, aminek mondjuk + 3) megvan-e a licenc + 4) hasznalhato-e
    for rel, entry in sorted(declared.items()):
        path = root / rel
        if not path.is_file():
            problems.append(f"DEKLARALT, de HIANYZO artefaktum: {rel}")
            continue

        actual = sha256_of(path)
        if actual != entry["sha256"]:
            problems.append(
                f"{rel}: a sha256 NEM egyezik a deklaralttal.\n"
                f"      deklaralt: {entry['sha256']}\n"
                f"      merve    : {actual}"
            )

        license_path = root / entry["license_file"]
        if not license_path.is_file():
            problems.append(f"{rel}: a deklaralt licenc-fajl HIANYZIK ({entry['license_file']})")
        elif entry["license"] == "OFL-1.1":
            text = license_path.read_text(encoding="utf-8", errors="replace")
            if "SIL OPEN FONT LICENSE" not in text.upper():
                problems.append(
                    f"{rel}: a licenc-fajl NEM az OFL szovege ({entry['license_file']})"
                )

        if path.suffix == ".ttf":
            report = font_report(path)
            if report["missing"]:
                problems.append(
                    f"{rel}: a betutipus NEM fedi a megkovetelt keszletet -- "
                    f"hianyzo: {''.join(report['missing'])}"
                )
            if report["present_control"]:
                problems.append(
                    f"{rel}: a POZITIV KONTROLL elbukott -- a merés olyan karaktert is "
                    f"megtalaltnak mond, aminek nem szabadna ott lennie "
                    f"({''.join(report['present_control'])}). A meres ERVENYTELEN."
                )
            if not report["embeddable"]:
                problems.append(
                    f"{rel}: a betutipus fsType={report['fs_type']} -- a beagyazas TILTOTT, "
                    f"tehat kereshető PDF-be nem tehető"
                )

    if not found:
        problems.append(
            "A kapu EGYETLEN kovetett binarist sem talalt. Ez nem 'tiszta', hanem "
            "gyanus: a bejaro valoszinuleg nem lat (rossz gyoker vagy git-hiba)."
        )

    return problems


def selftest(root: Path, manifest: dict) -> int:
    """A kapu bizonyítja, hogy HARAP — a mérőeszközre ugyanaz a mérce."""
    failures: list[str] = []

    font = root / "src/doccapture/resources/LiberationSans-Regular.ttf"
    if font.is_file():
        # negativ kontroll: egy olyan keszlet, amit a font BIZTOSAN nem fed
        report = font_report(font, charset="中ア")
        if not report["missing"]:
            failures.append("a glyph-meres NEM fog: a CJK-keszletet is fedettnek mondja")
        # pozitiv kontroll: a magyar keszlet fedve van
        report = font_report(font, charset=HUNGARIAN_CHARSET)
        if report["missing"]:
            failures.append(
                "a glyph-meres HAMISAN riaszt a magyar keszleten: "
                + "".join(report["missing"])
            )

    # a binaris-felismeres mindket iranyban
    if is_binary(root / "README.md"):
        failures.append("a binaris-felismeres a README.md-t binarisnak mondja")
    if font.is_file() and not is_binary(font):
        failures.append("a binaris-felismeres a .ttf-et NEM mondja binarisnak")

    print(f"Onteszt: {4 - len(failures)}/4 kontroll rendben.")
    if failures:
        print("\nA KAPU NEM AZT MERI, AMIT ALLIT:")
        for line in failures:
            print(f"  - {line}")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Binaris-artefaktum kapu")
    parser.add_argument("--root", default=str(REPO))
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))

    if args.selftest:
        return selftest(root, manifest)

    if selftest(root, manifest) != 0:
        print("\nA kapu ontesztje elbukott — az eredmenye nem ertelmezheto.")
        return 1
    print()

    problems = check(root, manifest)

    declared = manifest["artifacts"]
    print(f"Binaris-kapu: {len(declared)} deklaralt artefaktum\n")
    print(f"  {'ut':<52} {'licenc':<10} allapot")
    print("  " + "-" * 78)
    for entry in declared:
        path = root / entry["path"]
        allapot = "hianyzik"
        if path.is_file():
            allapot = "EGYEZIK" if sha256_of(path) == entry["sha256"] else "ELTER"
        print(f"  {entry['path']:<52} {entry['license']:<10} {allapot}")

    font = root / "src/doccapture/resources/LiberationSans-Regular.ttf"
    if font.is_file():
        report = font_report(font)
        print(
            f"\n  betutipus-fedes: {report['measured']} karakter megmerve, "
            f"{len(report['missing'])} hianyzik · fsType={report['fs_type']} "
            f"(beagyazhato: {'igen' if report['embeddable'] else 'NEM'})"
        )

    print()
    if problems:
        print("⚠ A BINARIS-KAPU ELBUKOTT:")
        for line in problems:
            print(f"  - {line}")
        return 1

    print("Binaris-kapu: TISZTA")
    print(
        "  ⚠ Amit ez NEM mer: a licenc JOGI ertelmezeset, a betutipus vizualis\n"
        "     minoseget, es a modositott szarmazek atnevezesi kotelezettseget\n"
        "     (ma nem modositunk betutipust)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
