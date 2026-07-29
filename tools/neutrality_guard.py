#!/usr/bin/env python3
"""Semlegessegi kapu — a csomag akkor eladhato, ha barmely iparagban hasznalhato.

Miert gepi kapu es nem review-figyelem: a markanev es az iparagi szo eszrevetlenul
bennmarad, mert olvasaskor termeszetesnek tunik -- eppen az szurodik at, ami a
szerzonek magatol ertetodo. A semlegesseget merni kell, nem figyelni.

A kapu a FORRAST nezi, nem a viselkedest: a markanev akkor is hiba, ha eppen
semmi nem hivatkozik ra.

A szokeszlet KONFIGURACIO (`neutrality.json`), nem beegetett lista -- ugyanaz az
elv, amit a motor a cel-rendszerre es a mezonevekre is alkalmaz. Ugyfelnevek a
verziokovetett configba NEM kerulnek: azok telepitesenkent masok, es egy nyilvanos
repoban ugyfel-kapcsolatot fednenek fel. Bovites: `neutrality.local.json`
(gitignore-olt), amit a kapu automatikusan hozzaolvas, ha letezik.

Futtatas:
    python tools/neutrality_guard.py [--root SRC] [--config tools/neutrality.json]

Kilepesi kod: 0 = tiszta, 1 = talalt tiltott szot.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# A provenancia-kommentek erteket hordoznak (honnan lett altalanositva egy
# megoldas), ezert nem buknak el. Csak kommentben, es csak jelolessel.
PROVENANCE_MARKER = "provenance:"

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
SCAN_SUFFIXES = {".py", ".toml", ".cfg", ".md", ".yaml", ".yml", ".json"}

# A kapu sajat fajljai: a tiltolista definicioja nem lehet sajat maga sertese.
SELF_FILES = {"neutrality_guard.py", "neutrality.json", "neutrality.local.json"}


def load_forbidden(config_path: Path) -> dict[str, tuple[str, ...]]:
    """Szokeszlet betoltese, a lokalis bovitessel egyutt."""
    with config_path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    forbidden: dict[str, list[str]] = {
        category: list(words) for category, words in data["forbidden"].items()
    }

    local_path = config_path.with_name("neutrality.local.json")
    if local_path.exists():
        with local_path.open(encoding="utf-8") as handle:
            local = json.load(handle)
        for category, words in local.get("forbidden", {}).items():
            forbidden.setdefault(category, []).extend(words)

    return {category: tuple(words) for category, words in forbidden.items()}


def scan_file(path: Path, forbidden: dict[str, tuple[str, ...]]) -> list[tuple[int, str, str, str]]:
    """(sor, kategoria, szo, sor-tartalom) talalatok egy fajlban."""
    hits: list[tuple[int, str, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits

    for lineno, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if PROVENANCE_MARKER in lowered:
            continue
        for category, words in forbidden.items():
            for word in words:
                # Szo-hatar, hogy egy rovid szo ne fogjon meg hosszabbat.
                if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", lowered):
                    hits.append((lineno, category, word, line.strip()))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Semlegessegi kapu")
    parser.add_argument("--root", default=".", help="vizsgalando gyoker")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("neutrality.json")),
        help="szokeszlet",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    forbidden = load_forbidden(Path(args.config).resolve())
    findings: list[tuple[Path, int, str, str, str]] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SELF_FILES:
            continue
        for lineno, category, word, line in scan_file(path, forbidden):
            findings.append((path.relative_to(root), lineno, category, word, line))

    if not findings:
        print("Semlegessegi kapu: TISZTA")
        return 0

    print(f"Semlegessegi kapu: {len(findings)} TALALAT\n")
    for rel, lineno, category, word, line in findings:
        print(f"  {rel}:{lineno}  [{category}] '{word}'")
        print(f"      {line}")
    print(
        "\nA motor iparag-agnosztikus: marka-, iparagi es ugyfelnev nem kerulhet bele.\n"
        "A cel-rendszer, a partner-azonositok es a mezonevek KONFIGURACIO.\n"
        "Provenancia-kommentnel hasznald a 'provenance:' jelolest."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
