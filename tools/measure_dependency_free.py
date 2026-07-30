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
)

DEFAULT_BLOCKED = ("openpyxl",)


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
    args = parser.parse_args()
    blocked = tuple(args.block) if args.block else DEFAULT_BLOCKED

    # A repo gyokere es a `src` a keresesi utra -- kulonben a `tests` csomag nem
    # importalhato, es 8 "hiba" latszana meresi eredmeny helyett.
    for entry in (str(REPO), str(REPO / "src")):
        if entry not in sys.path:
            sys.path.insert(0, entry)

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


if __name__ == "__main__":
    raise SystemExit(main())
