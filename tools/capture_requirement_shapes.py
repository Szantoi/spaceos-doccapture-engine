"""A `Requires-Dist` ALAKOK rögzítése valódi csomagokból — a licenc-kapu mérőmintája.

MIÉRT LÉTEZIK — EGY MÉRT, KÖRNYEZET-FÜGGŐ VAKSÁG
------------------------------------------------
A licenc-kapu zárvány-bejárását egy **végponttól végpontig** mérő teszt őrzi: a
`transitive_closure` egy valódi csomag-gráfon se hozza be a dev/docs/test
extrákat. Ez a teszt a `reportlab` csomagot használta mérőmintának — az viszont
**a fejlesztői gépen telepítve van, a CI-n nincs**. A CI ezért 2026-07-31-én
elbukott, és a mérés addig **csendben** attól függött, mi van a gépen.

⚠ **A tanulság nem az volt, hogy rossz csomagot választottunk.** Végigmérve: a
motor teljes telepített láncán (`openpyxl`, `et-xmlfile`, `pypdfium2`,
`packaging`) **NULLA** extra-feltételű követelmény van — vagyis a CI-n
**egyáltalán nincs alkalmas valódi mérőminta**. A mérés tehát csak úgy lehet
környezet-független, ha a mintát **magunkkal visszük**.

MIT CSINÁL EZ AZ ESZKÖZ
-----------------------
Kiolvassa a megnevezett, valódi telepített csomagok `Requires-Dist` sorait, és
`tests/requirement_shapes.json`-ba írja őket **betű szerint** — egyetlen
átalakítással: minden csomag-NÉV elé `dcfixture-` előtag kerül (a névütközés
elkerülésére, ld. lent). A marker-kifejezés, a verzió-korlát és a köztes
szóközök **érintetlenek**.

MIÉRT KELL A NÉV-ELŐTAG
-----------------------
A `transitive_closure` **név szerint** old fel (`metadata.distribution(name)`).
Ha a minta a valódi neveket hordozná, akkor egy olyan gépen, ahol a `pillow`
történetesen telepítve van, a bejárás **a valódi pillow-ba** lépne tovább, és a
mérés ismét attól függene, mi van a gépen — vagyis pont a javítani kívánt hibát
hoznánk vissza. Az előtag ezt zárja ki: a minta-nevek **sehol nem létezhetnek**
telepített csomagként.

MIÉRT NEM ÍRTAM KÉZZEL A MINTÁT
-------------------------------
Mert a kézzel írt kontroll a **saját képzeletemet** méri, nem a valóságot. A
rögzítés négy olyan alakot hozott elő, amit nem találtam volna ki:

1. **Kétféle idézőjel** ugyanarra a feltételre: `extra == "accel"` (reportlab)
   és `extra == 'docs'` (pillow).
2. **ÖSSZETETT marker:** `(python_version < "3.10") and extra == 'typing'` —
   környezeti feltétel ÉS extra egy sorban. Egy naiv „tartalmazza-e az
   `extra ==` szöveget" vizsgálat ezen a soron rossz irányba dönthet.
3. **Eltérő tagolás:** `sphinx >=7.3 ; extra == 'docs'` — szóköz a `;` előtt és
   a verzió-korlát előtt is; máshol `rl_accel<1.1,>=0.9.0; extra == "accel"`.
4. **Ugyanaz a csomag több extra alatt** (`olefile`: docs / fpx / mic / tests).

Használat:
    python tools/capture_requirement_shapes.py            # kiirja, mit talalt
    python tools/capture_requirement_shapes.py --write    # frissiti a JSON-t
"""

from __future__ import annotations

import argparse
import json
import re
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "tests" / "requirement_shapes.json"

PREFIX = "dcfixture-"

# A minta-graf szerepei. A HARMAT egyutt az teszi hasznalhatova, hogy a bejaras
# MINDHAROM viselkedeset meri: feltetel nelkuli kovetes, extra-feltetelu
# kihagyas, es a kihagyas MELYSEG-2-ben is (a 77 hamis "nem mertem" annak
# idejen eppen a melyebb szinteken keletkezett).
SOURCES = (
    ("reportlab", PREFIX + "root", "gyoker: 2 feltetel nelkuli + 6 extra-feltetelu kovetelmeny"),
    ("pillow", PREFIX + "imaging", "melyseg-2: csupa extra-feltetelu, kozte OSSZETETT marker"),
    ("charset-normalizer", PREFIX + "charset", "level: nincs egyetlen kovetelmenye sem"),
)

# A gyoker feltetel nelkuli kovetelmenyei ezekre a minta-nevekre mutatnak. Az
# alias azert kell, hogy a graf OSSZE legyen kotve: a `pillow>=9.0.0` sornak a
# `dcfixture-imaging` csomophoz kell vezetnie, nem egy `dcfixture-pillow`
# nevu, nem letezo csomaghoz.
ALIASES = {
    "reportlab": PREFIX + "root",
    "pillow": PREFIX + "imaging",
    "charset-normalizer": PREFIX + "charset",
}

# ----------------------------------------------------------------------
# LICENC-ALAKOK -- a masodik, ugyanilyen kornyezet-fuggo vaksag
# ----------------------------------------------------------------------
# A kapu legertekesebb tesztje egy TENYLEG TELEPITETT GPL-es csomagon merte,
# hogy a kapu elbukik. A fejlesztoi gepen ot ilyen van; egy tiszta CI-n NULLA --
# ott a teszt `skipUnless`-szel KIMARAD, es mivel a merési kor `KIHAGYVA=0`-t
# kovetel, a kor emiatt PIROS. Ugyanaz az osztaly, mint a kovetelmeny-alakoknal,
# csak a tunete nem bukas, hanem szamolt kihagyas.
#
# Az ot rogzitett minta egyben ERŐSEBB is az eredetinel: az eredeti azt vette,
# amelyik eloszor akadt a kezebe (kornyezet-fuggo, nem determinisztikus), ez
# viszont `license_of` MINDHAROM forras-mezojet lefedi -- `License-Expression`,
# `Classifier` es `License` --, sot a ket mezot EGYSZERRE hordozo alakot is.
LICENSE_SOURCES = (
    ("surya-ocr", "License + Classifier egyutt (GPLv3)"),
    ("pymupdf", "csak License, es az DUAL licenc -- a tiltas kell hogy nyerjen"),
    ("semgrep", "csak License-Expression (SPDX)"),
    ("python-bidi", "csak Classifier"),
    ("crc32c", "License + Classifier egyutt (LGPLv2+)"),
)

LICENSE_PREFIX = PREFIX + "lic-"

# A licenc-hordozo mezok, `license_of` olvasasi sorrendjeben. A rogzites NYERS
# erteket ment: az osztalyozas elvarasa a TESZTBEN all, nem itt -- kulonben a
# mai viselkedest rogzitenenk elvarasnak, es a kapu sajat magat igazolna vissza.
LICENSE_FIELDS = ("License-Expression", "Classifier", "License")

_REQ_NAME = re.compile(r"^(\s*)([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """PEP 503 szerinti normalizálás — `Foo_Bar` és `foo-bar` ugyanaz a csomag."""
    return re.sub(r"[-_.]+", "-", name).lower()


def fixture_name(real_name: str) -> str:
    """Valódi csomag-név → minta-név. Alias, ha van; különben előtag."""
    key = normalize(real_name)
    return ALIASES.get(key, PREFIX + key)


def rewrite(line: str) -> str:
    """A követelmény-sor NEVÉT cseréli, mindent mást változatlanul hagy.

    Ez a függvény az egyetlen átalakítás a valódi metaadat és a minta között —
    szándékosan ennyire szűk, hogy a rögzített alak hitelessége eldönthető
    legyen egy pillantással.
    """
    match = _REQ_NAME.match(line)
    if not match:
        return line
    leading, name = match.group(1), match.group(2)
    return leading + fixture_name(name) + line[match.end() :]


def _distribution_or_none(name: str) -> metadata.Distribution | None:
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None


def capture_packages(provenance: list[dict], hianyzo: list[str]) -> dict[str, dict]:
    """A zárvány-bejárás minta-gráfja: `Requires-Dist` alakok, névcserével."""
    packages: dict[str, dict] = {}

    for real_name, fixture, role in SOURCES:
        dist = _distribution_or_none(real_name)
        if dist is None:
            hianyzo.append(real_name)
            continue
        raw = list(dist.requires or [])
        packages[fixture] = {
            "version": "1.0.0",
            "requires": [rewrite(line) for line in raw],
        }
        provenance.append(
            {
                "forras_csomag": real_name,
                "forras_verzio": dist.version,
                "minta_nev": fixture,
                "szerep": role,
                "kovetelmeny_sorok": len(raw),
            }
        )
    return packages


def capture_licenses(provenance: list[dict], hianyzo: list[str]) -> dict[str, dict]:
    """A licenc-hordozó mezők NYERS értéke, `license_of` olvasási sorrendjében."""
    specimens: dict[str, dict] = {}

    for real_name, role in LICENSE_SOURCES:
        dist = _distribution_or_none(real_name)
        if dist is None:
            hianyzo.append(real_name)
            continue

        md = dist.metadata
        fields: list[list[str]] = []
        for key in LICENSE_FIELDS:
            if key == "Classifier":
                fields.extend(
                    [key, value]
                    for name, value in md.items()
                    if name == "Classifier" and value.startswith("License ::")
                )
                continue
            value = (md.get(key) or "").strip()
            if value:
                # A `License` mezobe nemelyik csomag a TELJES licenc-szoveget
                # teszi; a kapu is csak az elso sorat hasznalja, es a minta se
                # hordozzon tobbet -- de a CSONKITAS teny, ezert kimondjuk.
                fields.append([key, value.splitlines()[0].strip()])

        fixture = LICENSE_PREFIX + normalize(real_name)
        specimens[fixture] = {"version": dist.version, "mezok": fields}
        provenance.append(
            {
                "forras_csomag": real_name,
                "forras_verzio": dist.version,
                "minta_nev": fixture,
                "szerep": role,
                "licenc_mezok": len(fields),
            }
        )
    return specimens


def capture() -> dict:
    """A valódi telepített csomagokból építi a két minta-készletet."""
    provenance: list[dict] = []
    hianyzo: list[str] = []

    packages = capture_packages(provenance, hianyzo)
    licenses = capture_licenses(provenance, hianyzo)

    if hianyzo:
        raise SystemExit(
            "A rogzites NEM teljes: nincs telepitve " + ", ".join(hianyzo) + ".\n"
            "Ez az eszkoz a fejlesztoi gepen fut (ott vannak meg a csomagok); a\n"
            "CI a mar rogzitett JSON-t hasznalja, es nem futtatja ezt az eszkozt."
        )

    return {
        "_megjegyzes": (
            "GEPPEL ROGZITETT alakok valodi csomagokbol -- ne szerkeszd kezzel. "
            "Ujra-rogzites: python tools/capture_requirement_shapes.py --write"
        ),
        "_atalakitas": (
            "Minden csomag-NEV ele '" + PREFIX + "' elotag kerult (nevutkozes ellen). "
            "A marker-kifejezes, a verzio-korlat, a tagolas es a licenc-mezok erteke "
            "BETU SZERINT valtozatlan (a tobbsoros `License` mezo elso soraig)."
        ),
        "_eredet": provenance,
        "csomagok": packages,
        "licenc_mintak": licenses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Requires-Dist alakok rogzitese")
    parser.add_argument("--write", action="store_true", help="a JSON frissitese")
    args = parser.parse_args()

    data = capture()

    total = sum(len(p["requires"]) for p in data["csomagok"].values())
    extras = sum(
        1
        for p in data["csomagok"].values()
        for line in p["requires"]
        if "extra ==" in line
    )
    print(
        f"Kovetelmeny-alakok: {len(data['csomagok'])} csomag, {total} sor, "
        f"ebbol {extras} extra-feltetelu"
    )
    print(f"Licenc-alakok     : {len(data['licenc_mintak'])} minta")
    for entry in data["_eredet"]:
        meret = entry.get("kovetelmeny_sorok")
        cimke = f"{meret} kovetelmeny-sor" if meret is not None else f"{entry['licenc_mezok']} licenc-mezo"
        print(
            f"  {entry['minta_nev']:<24} <- {entry['forras_csomag']} {entry['forras_verzio']}"
            f"  ({cimke})"
        )

    if not args.write:
        print("\n(--write nelkul nem irtam fajlt)")
        return 0

    TARGET.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"\nKiirva: {TARGET.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
