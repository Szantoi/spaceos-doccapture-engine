"""A licenc-kapu zárvány-bejárásának KÖRNYEZET-FÜGGETLEN mérőmintája.

MIÉRT LÉTEZIK
-------------
A `transitive_closure` végponttól végpontig mérése korábban a **telepített**
`reportlab` csomagra épült. Az a fejlesztői gépen megvan, a CI-n nincs — a CI
2026-07-31-én emiatt bukott, és a mérés addig **csendben** attól függött, mi van
a gépen.

⚠ **Nem csak rossz csomagot választottunk: a CI-n egyáltalán NINCS alkalmas
valódi minta.** Végigmérve a motor teljes telepített láncát (`openpyxl`,
`et-xmlfile`, `pypdfium2`, `packaging`): **nulla** extra-feltételű követelmény.
Ezért a mintát **magunkkal visszük** — ez a modul egy három csomagból álló,
szintetikus, de **valódi metaadatból rögzített** gráfot ír ideiglenes
könyvtárba, és a `sys.path`-ra teszi. Így a mérés minden gépen ugyanazt méri.

A HÁROM DOLOG, AMIT A MINTA MÉR
-------------------------------
1. a bejárás **követi** a feltétel nélküli követelményt (különben a kapu vakon
   zöld lenne: egy „soha semmit nem követek" bejárás is átmenne);
2. a bejárás **nem követi** az extra-feltételűt (ez volt az eredeti hiba: 77
   hamis „nem mértem" bejegyzés);
3. a kihagyás **mélység-2-ben is** áll — az eredeti hiba éppen a mélyebb
   szinteken keletkezett, ahol a dev/docs/test extrák tömege ül.

AMIT EZ A MINTA NEM MÉR — KIMONDVA
----------------------------------
1. **A valódi csomagok mai metaadatát nem.** A rögzítés pillanatképe
   (`reportlab 4.4.10`, `pillow 10.4.0`, `charset-normalizer 3.4.6`); ha ezek
   később más alakot vesznek fel, azt **semmi nem jelzi gépileg**. Az
   újra-rögzítés kézi lépés: `python tools/capture_requirement_shapes.py --write`.
2. **A valódi telepítés útját nem** (wheel, `.pth`, szerkeszthető telepítés) —
   a minta `.dist-info` könyvtárakat ír, ahogy az `importlib.metadata` várja.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import sys
import tempfile
from pathlib import Path

SHAPES_PATH = Path(__file__).resolve().parent / "requirement_shapes.json"

_DATA = json.loads(SHAPES_PATH.read_text(encoding="utf-8"))
PACKAGES: dict[str, dict] = _DATA["csomagok"]
LICENSE_SPECIMENS: dict[str, dict] = _DATA["licenc_mintak"]
PROVENANCE: list[dict] = _DATA["_eredet"]

# A minta-graf gyokere: az a csomag, amelyiknek FELTETEL NELKULI kovetelmenyei
# vannak. A rogzito eszkoz ezt a szerepet a `reportlab`-ra osztotta.
ROOT = "dcfixture-root"

# A telepitettnek szant csomagok -- ezeket irjuk ki .dist-info-kent.
INSTALLED: frozenset[str] = frozenset(PACKAGES)


def _requirement_name(line: str) -> str:
    """A követelmény-sor csomag-neve (a verzió-korlát és a marker előtti rész)."""
    head = line.split(";")[0].strip()
    for separator in ("<", ">", "=", "!", "~", "[", " "):
        head = head.split(separator)[0]
    return head.strip()


def _is_conditional(line: str) -> bool:
    """Feltételes-e a sor — SZÁNDÉKOSAN durvább szabállyal, mint a mért kód.

    A licenc-kapu a markert szabvány szerint **kiértékeli** (`packaging`); ez az
    elvárás-oldal viszont csak annyit néz, van-e `;` a sorban. A két szabálynak
    **külön kell tévednie** — ha az elvárást ugyanazzal a logikával számolnám ki,
    amit mérek, a teszt a saját hibáját igazolná vissza.

    A durva szabály érvényessége ezen a rögzített adaton **mérve van**
    (`test_a_MINTA_minden_feltetelES_sora_extra_feltetelU`): itt minden `;`-es
    sor tartalmaz `extra ==` feltételt, tehát a két szabály ezen az adaton
    egybeesik. Egy tisztán környezeti marker (`; python_version >= "3.11"`)
    elrontaná — ezért méri külön teszt, hogy ilyen nincs a mintában.
    """
    return ";" in line


def expected_closure() -> set[str]:
    """A gyökérből feltétel nélküli éleken elérhető csomagok — az ELVÁRÁS."""
    reachable: set[str] = set()
    queue = [ROOT]
    while queue:
        name = queue.pop()
        if name in reachable or name not in PACKAGES:
            continue
        reachable.add(name)
        for line in PACKAGES[name]["requires"]:
            if not _is_conditional(line):
                queue.append(_requirement_name(line))
    return reachable


def extra_only_names() -> set[str]:
    """Csak extra-feltétel mögött álló nevek — ezek EGYIKE SEM kerülhet a zárványba.

    Egyik sincs „telepítve", tehát ha a marker-kiértékelés elromlik, ezek a
    **nem mért** listára kerülnek — pontosan az eredeti hiba tünete (77 hamis
    „nem mértem" bejegyzés).
    """
    names: set[str] = set()
    for package in PACKAGES.values():
        for line in package["requires"]:
            if _is_conditional(line):
                names.add(_requirement_name(line))
    return names - INSTALLED


def _write_dist_info(
    destination: Path,
    name: str,
    version: str,
    extra_fields: list[list[str]] | None = None,
    requires: list[str] | None = None,
) -> None:
    """Egy `.dist-info` könyvtár, ahogy az `importlib.metadata` várja."""
    folder = destination / f"{name.replace('-', '_')}-{version}.dist-info"
    folder.mkdir(parents=True)
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
    ]
    # A licenc-hordozo mezok a ROGZITETT sorrendben -- a `Classifier` tobbszor is
    # allhat, ezert lista, nem szotar.
    lines.extend(f"{key}: {value}" for key, value in (extra_fields or []))
    lines.extend(f"Requires-Dist: {requirement}" for requirement in (requires or []))
    (folder / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")


def materialize(destination: Path) -> None:
    """Mindkét minta-készletet kiírja `.dist-info` könyvtárakként.

    A licenc-minták **nem érhetők el** a `dcfixture-root`-ból (nincs rájuk
    követelmény-él), tehát a zárvány-mérést nem befolyásolják — de ugyanabban a
    könyvtárban állnak, így egy `PYTHONPATH` mindkét mérésnek elég.
    """
    for name, package in PACKAGES.items():
        _write_dist_info(destination, name, package["version"], requires=package["requires"])
    for name, specimen in LICENSE_SPECIMENS.items():
        _write_dist_info(destination, name, specimen["version"], extra_fields=specimen["mezok"])


@contextlib.contextmanager
def installed_specimen():
    """A minta-gráf „telepítése" a mérés idejére.

    ⚠ A takarítás azért kötelező, mert a minta-nevek egyébként **átszivárognának**
    a suite többi mérésébe: a licenc-kapu a saját láncát járja be, és egy bent
    ragadt `sys.path`-bejegyzés csendben megváltoztatná, mit lát.
    """
    with tempfile.TemporaryDirectory(prefix="dcfixture-") as raw:
        destination = Path(raw)
        materialize(destination)

        sys.path.insert(0, str(destination))
        importlib.invalidate_caches()
        try:
            yield destination
        finally:
            with contextlib.suppress(ValueError):
                sys.path.remove(str(destination))
            importlib.invalidate_caches()
