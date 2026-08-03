"""A függőség-mentesség MÉRÉSE — nem állítása.

MIT ÁLLÍTUNK, ÉS MIÉRT KELL HOZZÁ MÉRÉS
---------------------------------------
A `README.md` és a `pyproject.toml` azt állítja, hogy **a mag és az elválasztott
szöveges út külső csomag nélkül működik**. Ez piaci előny (a cégek integrálásának
leggyakoribb bemenete telepítési kockázat nélkül kezelhető), tehát nem elég
hinni benne.

A mérés két lépésből áll, és a sorrend a lényeg:

1. **negatív kontroll:** bizonyítjuk, hogy a blokkoló **tényleg fog** — ha az
   opcionális csomag mégis importálható lenne, a mérés **semmit nem állít**, és
   ezt kimondjuk, nem „sikeresnek" nevezzük;
2. a függőség-mentesnek szánt teszt-modulok futtatása a blokkolt környezetben.

⚠ **A `kihagyva=0` ugyanolyan fontos, mint a `bukas=0`.** A `skipUnless`-szel
védett tesztek csendben kimaradhatnak, és akkor a suite **zöld** — miközben
semmit nem mért. Ez az „üresen zöld számláló", és ez az eszköz kiírja.

Használat:
    python tools/measure_dependency_free.py
    python tools/measure_dependency_free.py --block openpyxl --block valami_mas
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# A fuggoseg-mentesnek szant modulok. Ez a lista a CI-ben IS ez -- ket kulon
# lista ket igazsag lenne ugyanarrol, es az egyik elobb-utobb elcsuszna.
DEPENDENCY_FREE_MODULES = (
    "tests.test_models",
    "tests.test_config",
    "tests.test_core_boundary",
    "tests.test_ports",
    "tests.test_observability",
    "tests.test_principles",
    "tests.test_source_hygiene",
    "tests.test_tabular_schema",
    "tests.test_tabular_values",
    "tests.test_tabular_delimited",
    "tests.test_load_tabular",
    "tests.test_document_detect",
    "tests.test_document_consistency",
    "tests.test_analyze_document",
    "tests.test_contract",
    "tests.test_measurement_completeness",
    "tests.test_columns",
    # A binaris-artefaktum kapu fuggoseg-mentes: a betutipust sajat, stdlib-only
    # cmap-olvasoval meri (`struct`), eppen azert, hogy a MERES ne fuggjon attol,
    # telepitve van-e barmilyen font-konyvtar.
    "tests.test_binary_artifacts",
)

# ⚠ A blokkolo-lista MINDEN opcionalis csomagot fedjen. Ha egy uj extra csomagja
# kimarad innen, a "fuggoseg nelkul" kor CSENDBEN hasznalna -- es a szam pont
# azt allitana, amit nem mert. A `document` extra csomagja ezert itt van.
DEFAULT_BLOCKED = ("openpyxl", "pypdfium2")

# Az EXTRAT igenylo korok. Ezek a listak SZANDEKOSAN itt allnak, nem a
# teszt-fajlban: a koroket ez az eszkoz futtatja, tehat a "mi tartozik melyik
# korbe" kerdesnek ITT van a forras-igazsaga. A teljesseg-kapu
# (`tests/test_measurement_completeness.py`) INNEN importalja mindharmat --
# igy egy uj teszt-modul felvetele egy helyen tortenik.
#
# ⚠ A `document` kor a DC-01a-ban jott letre. Elotte a munkafuzet-lista a
# teszt-fajlban allt literalkent, az eszkoz pedig nem tudott rola -- vagyis a
# ket helyen ket kulonbozo tudas volt ugyanarrol a felosztasrol.
WORKBOOK_DEPENDENT_MODULES = ("tests.test_tabular_workbook",)
# A licenc-kapu tesztje ALPROCESSZBEN futtatja a kaput, es exit 0-t var. A kapu
# viszont elbukik, ha egy DEKLARALT fuggoseg nincs telepitve ("egy nem mert
# fuggoseg nem rendben") -- tehat ez a modul strukturalisan NEM a fuggoseg-mentes
# korbe valo, hanem oda, ahol az extrak mar fent vannak.
#
# ⚠ Miert nem derult ki fejlesztoi gepen: a fuggoseg-mentes kor az importokat a
# SAJAT folyamataban blokkolja, az alprocessz viszont nem orokli a blokkolast --
# ahol az extrak globalisan telepitve vannak, ott a teszt ZOLD marad. A CI-n, ahol
# tenyleg nincsenek telepitve, azonnal kiderult. (Root-lelet, 2026-07-31.)
DOCUMENT_DEPENDENT_MODULES = ("tests.test_text_layer", "tests.test_license_guard")

# Kor-nev -> (modulok, a kor ALTAL IGENYELT csomagok). Az igenyelt csomagokat
# a kor elejen KIMONDVA ellenorizzuk: ha egy `skipUnless`-szel vedett modul
# fuggosege hianyzik, a suite ZOLD maradna, es semmit nem mert volna.
EXTRA_ROUNDS = {
    "workbook": (WORKBOOK_DEPENDENT_MODULES, ("openpyxl",)),
    "document": (DOCUMENT_DEPENDENT_MODULES, ("pypdfium2",)),
}


class _BlockingFinder:
    """Meta-path kereső, ami a megadott csomagokat elérhetetlenné teszi."""

    def __init__(self, blocked: tuple[str, ...]) -> None:
        self._blocked = blocked

    def find_spec(self, name: str, path=None, target=None):  # noqa: ANN001 - importlib API
        root = name.split(".")[0]
        if root in self._blocked:
            raise ImportError(f"{root} szandekosan blokkolva a meres kedveert")
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fuggoseg-mentesseg merese")
    parser.add_argument(
        "--block",
        action="append",
        default=None,
        help="blokkolando csomag (tobbszor is megadhato)",
    )
    parser.add_argument(
        "--round",
        choices=("free", *EXTRA_ROUNDS),
        default="free",
        help="melyik merési kor fusson (alapertelmezes: free)",
    )
    args = parser.parse_args()

    # A repo gyokere es a `src` a keresesi utra -- kulonben a `tests` csomag nem
    # importalhato, es 8 "hiba" latszana meresi eredmeny helyett.
    for entry in (str(REPO), str(REPO / "src")):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    if args.round != "free":
        return _run_extra_round(args.round)

    blocked = tuple(args.block) if args.block else DEFAULT_BLOCKED
    sys.meta_path.insert(0, _BlockingFinder(blocked))

    # 1) NEGATIV KONTROLL -- enelkul a meres semmit nem allit.
    for package in blocked:
        try:
            __import__(package)
        except ImportError:
            print(f"negativ kontroll: a blokkolo fog ({package} nem importalhato)")
        else:
            print(
                f"⚠ A BLOKKOLO NEM FOG: a(z) {package!r} megis importalhato. "
                f"A meres ERVENYTELEN — nem 'sikeres'."
            )
            return 2

    # 2) A fuggoseg-mentes modulok futtatasa
    suite = unittest.defaultTestLoader.loadTestsFromNames(DEPENDENCY_FREE_MODULES)
    result = unittest.TextTestRunner(verbosity=1).run(suite)

    print(
        f"\nFUGGOSEG NELKUL: futott={result.testsRun} bukas={len(result.failures)} "
        f"hiba={len(result.errors)} KIHAGYVA={len(result.skipped)}"
    )
    if result.skipped:
        # A kihagyas ugyanolyan sulyos, mint a bukas: a suite zold lenne, es
        # semmit nem mert volna.
        print("⚠ A kihagyott tesztek uresen zold szamlalot adnanak:")
        for case, reason in result.skipped:
            print(f"    {case}: {reason}")
        return 1

    return 0 if result.wasSuccessful() else 1


def _run_extra_round(name: str) -> int:
    """Egy EXTRAT igenylo kor: eloszor a fuggoseg megletet mondjuk ki.

    ⚠ A sorrend itt ugyanolyan fontos, mint a fuggoseg-mentes kornel, csak a
    masik iranyban: ott azt bizonyitjuk, hogy a csomag **nincs** meg (kulonben
    a meres semmit nem allit), itt azt, hogy **megvan** — mert ha hianyzik, a
    `skipUnless`-szel vedett tesztek CSENDBEN kimaradnanak, es a kor zold
    lenne ugy, hogy egyetlen sort sem mert.
    """
    modules, required = EXTRA_ROUNDS[name]

    for package in required:
        try:
            module = __import__(package)
        except ImportError as exc:
            print(
                f"⚠ A(z) {name!r} kor fuggosege HIANYZIK: {package} ({exc}). "
                f"A kor futtatasa ERVENYTELEN lenne — a vedett tesztek csendben "
                f"kimaradnanak, es a 'zold' semmit nem allitana."
            )
            return 2
        version = getattr(module, "__version__", None) or getattr(
            module, "V_PYPDFIUM2", "(ismeretlen verzio)"
        )
        print(f"pozitiv kontroll: a(z) {name!r} kor fuggosege megvan ({package} {version})")

    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=1).run(suite)

    print(
        f"\n{name.upper()} KOR: futott={result.testsRun} bukas={len(result.failures)} "
        f"hiba={len(result.errors)} KIHAGYVA={len(result.skipped)}"
    )
    if result.skipped:
        print("⚠ A kihagyott tesztek uresen zold szamlalot adnanak:")
        for case, reason in result.skipped:
            print(f"    {case}: {reason}")
        return 1

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
