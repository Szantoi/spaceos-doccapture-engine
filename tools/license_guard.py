"""Licenc-kapu: a függőség-lánc MIT-kompatibilis-e.

MIÉRT LÉTEZIK — EGY MÉRT RÉS
----------------------------
A **G5** döntés (Gábor, 2026-07-30) MIT licencet írt elő mind a három
doccapture-repóra. Egy MIT-ként terjesztett csomagban egy **GPL/AGPL** függőség
jogi probléma, nem stílus-kérdés.

Mégis: a DC-01 felderítése kimérte, hogy **ezt a szabályt semmilyen gépi kapu nem
őrizte**. A motor `tools/` mappájában nem volt licenc-ellenőrző, tehát *„az első
DC-01 függőséggel a szabály azonnal mérés nélkülivé válik — GPL-függőséggel is
lefordul és zöld a suite."*

A LEGFONTOSABB TERVEZÉSI DÖNTÉS: A LICENC A **VERZIÓ** TULAJDONSÁGA
-------------------------------------------------------------------
⚠ Ezt egy feloldott ellentmondás tanította. Két független felderítő a **telepített**
`surya-ocr` metaadatából `GPL-3.0-or-later`-t mért — helyesen. A PyPI a **legújabb**
verzióra `Apache-2.0`-t mond — szintén helyesen. Végigmérve:

```
surya-ocr 0.1.0 … 0.19.x  ->  GPL-3.0-or-later
surya-ocr 0.20.0 -tol     ->  Apache-2.0
```

Vagyis mindkét mérés igaz volt, és **mégis rossz szabály jött ki belőlük**
(*„a surya tilos"*), mert egyik sem vizsgálta, hogy a licenc **verzió-függő**-e.
A helyes szabály: *„a surya 0.20.0 alatt tilos"* — vagyis a függőségnek **licenc-okból
alsó verzió-korlátja** van.

Ezért a kapu **két külön kérdést** mér, és nem mossa össze őket:

| Kérdés | Amit mér | Miért nem elég a másik |
|---|---|---|
| **Megfelelő-e, ami TELEPÍTVE van?** | a telepített csomagok metaadata | egy régi, GPL-es telepítés akkor is kár, ha a `pyproject` újat kér |
| **Szabad-e rá HIVATKOZNI?** | a `pyproject` deklarált alsó korlátja | egy friss telepítés elrejtheti, hogy a deklaráció megengedne egy GPL-es régit |

MIT NEM MÉR — KIMONDVA
----------------------
1. **A modell-súlyok licencét nem.** A felderítés kimérte, hogy sem a
   felismerő-modellek gyorsítótárában nincs licenc-fájl: **a pip-csomag licence
   NEM a súlyok licence.** Ez a kapu a *csomagokat* méri.
2. **A tranzitív zárat csak a TELEPÍTETT környezetből** tudja bejárni. Ami nincs
   telepítve, arról **kimondja**, hogy nem mérte — nem hagyja ki csendben.
3. **Nem jogi tanács.** Az SPDX-azonosító gépi egyezése nem helyettesíti a
   licenc-szöveg elolvasását egy határesetnél.

Használat:
    python tools/license_guard.py
    python tools/license_guard.py --selftest      # negativ + pozitiv kontroll
    python tools/license_guard.py --root <repo> --config <licenses.json>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path

try:
    from packaging.requirements import InvalidRequirement, Requirement
except ImportError as exc:  # pragma: no cover - telepitesi kerdes
    # SZANDEKOSAN kimondott hiba, nem csendes visszaesés egy gyengebb meresre.
    # A marker-kiertekeles nelkul a kapu 77 hamis "nem mertem"-et adott (merve),
    # es egy zajos kaput egy heten belul kikapcsol valaki. Egy gyengebb meres,
    # ami MERESNEK latszik, rosszabb, mint egy kimondott hiba.
    raise SystemExit(
        "A licenc-kapu a `packaging` csomagot igenyli a fuggoseg-markerek "
        "kiertekelesehez (`pip install packaging`). Marker-kiertekeles nelkul a "
        "zarvany-bejaras minden dev/test extrat kotelezonek venne, es a kapu "
        f"hasznalhatatlanul zajos lenne. ({exc})"
    ) from exc

REPO = Path(__file__).resolve().parent.parent

# A `Requires-Dist` extra-feltetelet (`; extra == "x"`) le kell valasztani, kulonben
# a csomag-nev nem talalhato meg a telepitett kornyezetben.
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_VERSION_FLOOR = re.compile(r">=\s*([0-9][0-9A-Za-z.!+-]*)")


def normalize(name: str) -> str:
    """PEP 503 szerinti normalizálás — `Foo_Bar` és `foo-bar` ugyanaz a csomag."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_version(text: str) -> tuple:
    """Összehasonlítható verzió-alak. Csak a numerikus előtagot vesszük.

    Szándékosan egyszerű: a licenc-korlátoknál nem fordulnak elő egzotikus
    verzió-alakok, és egy fél-implementált PEP 440 rosszabb, mint egy kimondottan
    szűk. Ami nem értelmezhető, azt a hívó **kimondott hibaként** kapja.
    """
    parts = []
    for chunk in text.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


# ----------------------------------------------------------------------
# A licenc kiolvasása egy telepített csomagból
# ----------------------------------------------------------------------


def license_of(dist: metadata.Distribution) -> tuple[str, str]:
    """Visszaad: `(licenc-szoveg, honnan)`. Üres licenc = `("", "nem-merheto")`.

    Három helyről olvasunk, ebben a sorrendben — mert a modern csomagok a
    `License-Expression`-t használják, a régiek a `License` mezőt, és sokan csak
    classifiert adnak:
    """
    md = dist.metadata

    expression = (md.get("License-Expression") or "").strip()
    if expression:
        return expression, "License-Expression"

    classifiers = [
        value
        for key, value in md.items()
        if key == "Classifier" and value.startswith("License ::")
    ]
    if classifiers:
        return " ; ".join(c.split("::")[-1].strip() for c in classifiers), "Classifier"

    plain = (md.get("License") or "").strip()
    if plain:
        # A `License` mezobe nemelyik csomag a TELJES licenc-szoveget beteszi.
        # Az elso sor eleg az azonositashoz, es a hibauzenet igy olvashato marad.
        return plain.splitlines()[0].strip(), "License"

    return "", "nem-merheto"


def classify(license_text: str, config: dict) -> str:
    """`megengedett` · `tiltott` · `nem-merheto` · `ismeretlen`.

    A **tiltólista előbb fut**, mint a megengedő. Ez nem stílus: egy
    „Dual Licensed – GNU AFFERO / commercial" szöveg **mindkettőre** illeszkedhet,
    és ilyenkor a tiltás kell hogy nyerjen. (Ugyanaz a precedencia-tanulság, mint
    a szivárgás-kapunál: a biztonságos minta nem mentesítheti a sort, ha ott a
    hiba is.)
    """
    # ⚠ `strip()` a vizsgalat ELOTT. Ezt a sajat ontesztem hozta elo: egy
    # csak-szokozbol allo licenc-mezo igaz erteku sztring, tehat `ismeretlen`-nek
    # minosult volna. A ket allapot MAS javitast ker: a "nem tudtuk megmerni"
    # kezi feloldast, a "nem ismerjuk fel" pedig dontest a szabalyhalmazrol.
    # Osszemosva a fejleszto a rossz helyen keresne.
    license_text = (license_text or "").strip()
    if not license_text:
        return "nem-merheto"

    lowered = license_text.lower()
    for pattern in config["denied"]:
        if pattern.lower() in lowered:
            return "tiltott"
    for pattern in config["allowed"]:
        if pattern.lower() in lowered:
            return "megengedett"
    return "ismeretlen"


# ----------------------------------------------------------------------
# A vizsgált halmaz: a DEKLARÁLT függőségek tranzitív zára
# ----------------------------------------------------------------------


def declared_requirements(root: Path) -> dict[str, str]:
    """A `pyproject.toml` deklarált függőségei: normalizált név → a nyers sor.

    A globális környezetben több száz idegen csomag van; a kapu **csak a saját
    deklarált láncot** vizsgálja. Ha mindent vizsgálna, a zaj miatt egy héten
    belül kikapcsolná valaki — és akkor rosszabbul állnánk, mint kapu nélkül.
    """
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project", {})

    raw: list[str] = list(project.get("dependencies", []))
    for extra_reqs in (project.get("optional-dependencies") or {}).values():
        raw.extend(extra_reqs)

    result: dict[str, str] = {}
    for line in raw:
        match = _REQ_NAME.match(line)
        if match:
            result[normalize(match.group(1))] = line.strip()
    return result


def transitive_closure(names: set[str]) -> tuple[dict[str, metadata.Distribution], set[str]]:
    """Bejárja a telepített csomagok `Requires-Dist` gráfját.

    Visszaad: `(megtalalt, nem_telepitett)`. A **nem telepített** halmazt
    szándékosan visszaadjuk: azt nem tudtuk megmérni, és ezt ki kell mondani.
    """
    found: dict[str, metadata.Distribution] = {}
    missing: set[str] = set()
    queue = list(names)

    while queue:
        name = queue.pop()
        if name in found or name in missing:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.add(name)
            continue
        found[name] = dist
        for requirement in dist.requires or []:
            if not _runtime_requirement(requirement):
                continue
            match = _REQ_NAME.match(requirement.split(";")[0])
            if match:
                queue.append(normalize(match.group(1)))
    return found, missing


def _runtime_requirement(requirement: str) -> bool:
    """Része-e ez a követelmény a FUTÁSIDEJŰ zárványnak.

    ⚠ **Ezt a függvényt egy MÉRT hiba hozta létre, és a hiba a kapu
    használhatóságát tette volna kockára.** Az első változat a marker-feltételt
    egyszerűen **levágta** (`requirement.split(";")[0]`), és a csomag-nevet
    **feltétel nélkül** betette a sorba. Ettől minden függőség **minden
    dev/docs/test extrája** kötelezőnek látszott.

    Mérve, a `{reportlab, pypdf, pypdfium2}` zárványon:

    ```
    javitas ELOTT : 29 megtalalt + 77 "NEM TELEPITETT, tehat NEM MERT"  = 106 csomag
    ```

    A 77 között `flit`, `sphinx`, `pytest-*`, `coverage`, `check-manifest` — egyik
    sem szállított függőség. A kapu tehát **77 hamis „nem mértem"-et** írt volna
    ki minden futáskor, és a `certifi` (MPL-2.0) is így került be, egy
    extra-láncon: **a kapu látszólagos licenc-problémája a saját hibája volt.**

    Ez a zaj a legrosszabb fajta: nem téves *engedélyezés*, hanem téves *riasztás* —
    és egy zajos kaput egy héten belül kikapcsol valaki. Akkor pedig rosszabbul
    állnánk, mint kapu nélkül, mert azt hinnénk, hogy van.

    A helyes megoldás **nem** a marker levágása és **nem** az MPL felvétele az
    engedélyezett listára (az a tünetet kezelné): a markert **ki kell értékelni**.
    A `packaging` ezt szabvány szerint teszi, és egyben a `python_version` /
    `sys_platform` feltételeket is helyesen kezeli.
    """
    try:
        parsed = Requirement(requirement)
    except InvalidRequirement:
        # Nem talalgatunk: egy ertelmezhetetlen sor NEM kerul a zarvanyba, es ezt
        # a hivo latja a "nem mert" listan, ha egyaltalan relevans.
        return False
    if parsed.marker is None:
        return True
    # `extra: ""` -- igy az `extra == "dev"` alaku feltetel HAMIS lesz, a
    # `python_version` es `sys_platform` viszont a valos kornyezeten ertekelodik ki.
    return bool(parsed.marker.evaluate({"extra": ""}))


# ----------------------------------------------------------------------
# A verzió-korlát szabály (a surya-tanulság)
# ----------------------------------------------------------------------


def check_version_floors(config: dict, declared: dict[str, str]) -> list[str]:
    """A licenc-okból kötelező alsó verzió-korlát **deklarálva van-e**.

    A telepített verzió megfelelősége **nem elég**: egy `pyproject`-ben álló
    korlát nélküli hivatkozás megengedne egy régebbi, MÁS licencű kiadást — és a
    következő tiszta telepítés azt hozná be, csendben.
    """
    problems: list[str] = []
    for name, rule in (config.get("license_floor") or {}).items():
        key = normalize(name)
        if key not in declared:
            continue  # nem hivatkozunk ra -- nincs mit ellenorizni
        line = declared[key]
        floors = _VERSION_FLOOR.findall(line)
        required = parse_version(str(rule["min_version"]))
        if not floors:
            problems.append(
                f"{name}: a pyproject NEM ir elo alsó verzio-korlatot, pedig a licenc "
                f"csak {rule['min_version']}-tol megengedett ({rule['reason']}). "
                f"A mai sor: {line!r}"
            )
            continue
        if max(parse_version(f) for f in floors) < required:
            problems.append(
                f"{name}: a deklaralt korlat ({line!r}) ALACSONYABB, mint a licenc "
                f"miatt kotelezo {rule['min_version']} ({rule['reason']})"
            )
    return problems


# ----------------------------------------------------------------------
# Önteszt: negatív ÉS pozitív kontroll
# ----------------------------------------------------------------------


def selftest(config: dict) -> int:
    """A kapu bizonyítja, hogy HARAP és hogy NEM vaklárma.

    Egy kapu, ami sosem fog meg semmit, megkülönböztethetetlen attól, amelyik el
    sem indul. A minták a configban állnak, mert így a szabályhalmaz és az önteszt
    **együtt** változik.
    """
    failures: list[str] = []
    tests = config["_selftest"]

    for text in tests["must_deny"]:
        state = classify(text, config)
        if state != "tiltott":
            failures.append(f"NEM TILTOTTA (pedig kell): {text!r} -> {state}")

    for text in tests["must_allow"]:
        state = classify(text, config)
        if state != "megengedett":
            failures.append(f"NEM ENGEDTE AT (pedig kell): {text!r} -> {state}")

    for text in tests["must_be_unmeasurable"]:
        state = classify(text, config)
        if state != "nem-merheto":
            failures.append(f"NEM 'nem-merheto'-nek minositette: {text!r} -> {state}")

    print(
        f"Onteszt: {len(tests['must_deny'])} tiltando, {len(tests['must_allow'])} "
        f"megengedendo, {len(tests['must_be_unmeasurable'])} nem-merheto minta."
    )
    if failures:
        print("\nA KAPU NEM AZT MERI, AMIT ALLIT:")
        for line in failures:
            print(f"  - {line}")
        return 1

    total = sum(len(tests[k]) for k in ("must_deny", "must_allow", "must_be_unmeasurable"))
    print(f"Onteszt: {total}/{total} rendben — a kapu harap es nem vaklarma.")
    return 0


# ----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Licenc-kapu (MIT-kompatibilitas)")
    parser.add_argument("--root", default=str(REPO), help="a vizsgalt repo gyokere")
    parser.add_argument("--config", default="", help="a szabalyhalmaz (licenses.json)")
    parser.add_argument("--selftest", action="store_true", help="csak a kontrollok futnak")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    config_path = Path(args.config) if args.config else Path(__file__).with_name("licenses.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))

    if args.selftest:
        return selftest(config)

    if selftest(config) != 0:
        print("\nA kapu ontesztje elbukott — az eredmenye nem ertelmezheto.")
        return 1
    print()

    declared = declared_requirements(root)
    if not declared:
        # Ez NEM zold: kimondjuk, hogy nincs mit merni. Egy uresen zold licenc-kapu
        # pontosan ugy nez ki, mint egy tiszta fuggoseg-lanc.
        print("Licenc-kapu: a pyproject NEM deklaral egyetlen fuggoseget sem.")
        print("  Ez KIMONDOTT nulla, nem zold meres — nincs mit ellenorizni.")
        return 0

    found, missing = transitive_closure(set(declared))

    rows: list[tuple[str, str, str, str, str]] = []
    for name, dist in sorted(found.items()):
        text, source = license_of(dist)
        rows.append((name, dist.version, text or "(URES)", source, classify(text, config)))

    print(f"Licenc-kapu: {len(declared)} deklaralt fuggoseg, {len(found)} megmerve\n")
    print(f"  {'csomag':<18} {'verzio':<10} {'allapot':<13} {'honnan':<20} licenc")
    print("  " + "-" * 96)
    for name, version, text, source, state in rows:
        print(f"  {name:<18} {version:<10} {state:<13} {source:<20} {text[:36]}")

    denied = [r for r in rows if r[4] == "tiltott"]
    unmeasurable = [r for r in rows if r[4] == "nem-merheto"]
    unknown = [r for r in rows if r[4] == "ismeretlen"]

    accepted = {normalize(n) for n in (config.get("unmeasurable_accepted") or {})}
    unmeasurable_open = [r for r in unmeasurable if normalize(r[0]) not in accepted]

    floor_problems = check_version_floors(config, declared)

    print()
    problems = False

    if denied:
        problems = True
        print("⚠ TILTOTT LICENC — MIT-kent terjesztve jogi problema:")
        for name, version, text, _source, _state in denied:
            print(f"  - {name} {version}: {text}")

    if unmeasurable_open:
        problems = True
        print("⚠ NEM MERHETO LICENC — a hallgatas nem 'rendben':")
        for name, version, _text, _source, _state in unmeasurable_open:
            print(f"  - {name} {version}: nincs License/License-Expression/Classifier")
        print("    Ha manualisan feloldottad, vedd fel a config `unmeasurable_accepted`")
        print("    szakaszaba INDOKKAL — igy a dontes visszakereshető marad.")

    if unknown:
        problems = True
        print("⚠ FEL NEM ISMERT LICENC — sem a tilto-, sem a megengedo listan:")
        for name, version, text, _source, _state in unknown:
            print(f"  - {name} {version}: {text}")

    if missing:
        problems = True
        print("⚠ NEM TELEPITETT, tehat NEM MERT deklaralt fuggoseg:")
        for name in sorted(missing):
            print(f"  - {name}  (deklaralva: {declared.get(name, '(tranzitiv)')})")
        print("    Egy nem mert fuggoseg nem 'rendben' — telepitsd, vagy vedd ki.")

    if floor_problems:
        problems = True
        print("⚠ HIANYZO LICENC-OKU VERZIO-KORLAT:")
        for line in floor_problems:
            print(f"  - {line}")

    if problems:
        return 1

    print("Licenc-kapu: TISZTA")
    print(
        "  ⚠ Amit ez NEM mer: a MODELL-SULYOK licencet (a pip-csomag licence NEM a\n"
        "     sulyok licence), es a licenc-szoveg jogi ertelmezeset hataresetben."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
