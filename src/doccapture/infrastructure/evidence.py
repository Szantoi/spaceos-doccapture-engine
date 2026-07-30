"""Bizonyíték-lánc: relatív út + tartalom-hash (M13).

Miért az infrastruktúrában: ez az egyetlen hely, ahol fájlt olvasunk a
bizonyítékhoz. A magban ez nem lehet — ott a `SourceEvidence` csak azt írja le,
MI a bizonyíték, nem azt, hogyan állítjuk elő.

Miért kell a hash az útvonal mellé: az útvonal önmagában nem bizonyíték, mert a
fájl tartalma változhat. Egy későbbi eltérésnél a hash dönti el, hogy **a forrás
változott-e meg, vagy a kinyerésünk** — enélkül a kérdés eldönthetetlen, és
minden vita a mi szavunk ellen az ügyfél szava lesz.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from doccapture.core.errors import SourceUnreadableError
from doccapture.core.models import SourceEvidence
from doccapture.core.source_selection import require_relative

# 1 MiB. Streamelve olvasunk, mert egy nagy munkafuzet hasheleset nem szabad
# memoriaba olvasassal megfizetni -- es mert igy a hasheles koltsege fuggetlen
# a fajlmerettol a memoria oldalan.
_CHUNK_SIZE = 1024 * 1024

HASH_ALGORITHM = "sha256"
"""Egy helyen definiálva. Ha ez valaha változik, a régi bizonyítékok
összehasonlíthatatlanná válnak — ezért a hash **mellé** kiírjuk az algoritmust."""


def content_hash(path: Path) -> str:
    """A fájl tartalmának hashe, `<algoritmus>:<hex>` alakban.

    Az algoritmus-előtag nem díszítés: ha egyszer hash-t váltunk, egy előtag
    nélküli régi érték új értékkel összehasonlítva **eltérést** mutatna, és az
    úgy néz ki, mint egy megváltozott forrás. Az előtaggal látszik, hogy csak
    a mérőeszköz változott.
    """
    digest = hashlib.new(HASH_ALGORITHM)
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK_SIZE):
                digest.update(chunk)
    except OSError as exc:
        raise SourceUnreadableError(f"A forrás nem olvasható: {path.name} ({exc})") from exc
    return f"{HASH_ALGORITHM}:{digest.hexdigest()}"


def resolve_source(input_root: str, relative_path: str) -> Path:
    """Relatív útból tényleges fájl — a gyökérből ki nem lépve.

    A `require_relative` kapuja azért van előtte, mert egy `../../etc` alakú
    „relatív" út kilépne a bemeneti gyökérből, és onnantól bármit olvashatnánk.
    Csak olvasunk, tehát a kár korlátozott — de egy olvasás is szivárgás.
    """
    normalized = require_relative(relative_path)
    root = Path(input_root).resolve()
    candidate = (root / normalized).resolve()

    # Meg a `require_relative` utan is ellenorizzuk: symlink is kivezethet a
    # gyokerbol, es azt szoveg-vizsgalattal nem lehet eszrevenni.
    if root != candidate and root not in candidate.parents:
        raise SourceUnreadableError(
            f"A forrás a bemeneti gyökéren kívülre mutat: {relative_path!r}"
        )
    if not candidate.is_file():
        raise SourceUnreadableError(f"A forrás nem létező fájl: {relative_path!r}")
    return candidate


def evidence_for(
    input_root: str, relative_path: str, locator: Optional[str] = None
) -> SourceEvidence:
    """Bizonyíték egy forrásfájlhoz (és opcionálisan egy helyhez benne).

    ⚠ **Fájlonként egyszer hívd, ne cellánként.** A hash-elés végigolvassa a
    fájlt; egy 5000 soros munkafüzetnél cellánkénti hívás a fájlt tízezerszer
    olvasná végig. A cella-szintű bizonyítékot a `with_locator()` állítja elő
    a már kiszámolt hashből.
    """
    path = resolve_source(input_root, relative_path)
    return SourceEvidence(
        relative_path=require_relative(relative_path),
        content_hash=content_hash(path),
        locator=locator,
    )


def with_locator(evidence: SourceEvidence, locator: str) -> SourceEvidence:
    """Ugyanaz a fájl-bizonyíték, más hellyel benne (lap, sor, cella).

    Miért külön függvény és nem `dataclasses.replace`: így egy helyen látszik,
    hogy a **hash nem számolódik újra** — a fájl ugyanaz, csak máshová
    mutatunk benne.
    """
    return SourceEvidence(
        relative_path=evidence.relative_path,
        content_hash=evidence.content_hash,
        locator=locator,
    )
