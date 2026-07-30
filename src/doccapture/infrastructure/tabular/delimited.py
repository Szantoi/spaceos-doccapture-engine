"""Elválasztott szöveg (CSV és társai) olvasása — **függőség nélkül**.

Ez az adapter a szabványkönyvtárat használja, semmi mást. Érdemes kimondani:
egy cég integrálásának leggyakoribb bemenete így **külső csomag nélkül**
kezelhető, tehát a motor legszélesebb piacú útja a legkevesebb telepítési
kockázattal jár.

AMIT NEM TALÁLGATUNK
--------------------
- **Kódolás:** jelöltek sorrendben, az első használható nyer. Ha egyik sem, a
  hiba kimondott. Kódlap-alapú kódolás szándékosan nincs az alapértelmezésben:
  azok **soha nem buknak el**, tehát elnyelnék a valódi kódolási hibát.
- **Elválasztó:** a **fejléc-sor** dönti el, determinisztikus szabállyal
  (ld. `_delimiter_from_header`). A szabványkönyvtár felismerőjét szándékosan
  NEM használjuk: nem bukik el, ha nem tudja eldönteni, hanem **tippel** — és a
  tippjébe a szóköz is belefér. Holtversenynél és jelölt hiányában kimondott
  hibát dobunk, mert egy rossz elválasztóval az egész fájl egyetlen oszlop
  lesz, és a hiba a séma-illesztésnél jelenne meg, értelmezhetetlen üzenettel.
"""

from __future__ import annotations

import csv
from typing import Optional

from doccapture.core.config import CaptureConfig
from doccapture.core.errors import SourceUnreadableError
from doccapture.core.ports import TabularReader
from doccapture.core.tabular.assembly import build_result
from doccapture.core.tabular.result import TabularReadResult
from doccapture.core.tabular.schema import TableSchema
from doccapture.infrastructure.evidence import evidence_for, resolve_source, with_locator

class DelimitedTabularReader(TabularReader):
    """`TabularReader` elválasztott szöveges fájlokra."""

    def __init__(self, config: Optional[CaptureConfig] = None) -> None:
        self._config = config or CaptureConfig()
        # Fail-fast: a hibas beallitas most bukjon el, ne az elso fajlnal.
        self._config.tabular.validate()

    def read(self, relative_path: str, schema: TableSchema) -> TabularReadResult:
        options = self._config.tabular
        path = resolve_source(self._config.input_root, relative_path)
        text = self._decode(path)
        lines = text.splitlines()

        header_index = options.header_row - 1
        if header_index >= len(lines):
            raise SourceUnreadableError(
                f"A fejléc a(z) {options.header_row}. sorban lenne, de a fájlnak "
                f"csak {len(lines)} sora van: {relative_path!r}"
            )

        diagnostics: list[str] = []
        if options.delimiter:
            delimiter = options.delimiter
        else:
            delimiter, note = self._delimiter_from_header(
                lines[header_index], options.delimiter_candidates, path.name
            )
            if note:
                diagnostics.append(note)

        grid = list(csv.reader(lines, delimiter=delimiter))

        # Utolagos ellenorzes MEGADOTT elvalasztonal is: enelkul a kovetkezo hiba
        # a sema-illesztesnel jelenne meg ("kotelezo oszlop nincs meg"), es a
        # fejleszto a FAJLT keresne, pedig az elvalaszto volt rossz.
        if len(grid[header_index]) < 2:
            raise SourceUnreadableError(
                f"A(z) {delimiter!r} elválasztóval a fejléc-sor egyetlen mezőre "
                f"esik: {grid[header_index]}. Az elválasztó nincs benne a "
                f"fejlécben — add meg a `delimiter` beállításban. "
                f"(Egyoszlopos táblázat betöltése ma nem támogatott.)"
            )

        first_data_index = header_index + 1 + options.data_starts_after_header
        # A sorszam 1-alapu es a FAJL szerinti -- nem a sajat szamlalonk. Ha a
        # sajatunkat hasznalnank, a kihagyott sorok utan a bizonyitek rossz
        # helyre mutatna, es epp ellenorzeskor derulne ki, hogy nem stimmel.
        data_rows = [
            (index + 1, row) for index, row in enumerate(grid) if index >= first_data_index
        ]

        file_evidence = evidence_for(self._config.input_root, relative_path)

        return build_result(
            header_cells=list(grid[header_index]),
            data_rows=data_rows,
            schema=schema,
            options=options,
            file_evidence=file_evidence,
            locator_for=lambda row, column: f"R{row}C{column + 1}",
            header_locator=f"R{options.header_row}",
            human_only_field_types=self._config.human_only_field_types,
            evidence_with_locator=with_locator,
            extra_diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------

    def _decode(self, path) -> str:
        """Dekódolás a jelöltek sorrendjében. Az elsőt fogadjuk el, ami sikerül."""
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SourceUnreadableError(f"A fájl nem olvasható: {path.name} ({exc})") from exc

        attempted: list[str] = []
        for encoding in self._config.tabular.encoding_candidates:
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, LookupError) as exc:
                attempted.append(f"{encoding} ({type(exc).__name__})")

        raise SourceUnreadableError(
            f"Egyetlen kódolás-jelölttel sem dekódolható: {path.name}. "
            f"Megkísérelve: {attempted}. Ha tudod a fájl kódolását, vedd fel az "
            f"`encoding_candidates` listára — de tudd, hogy egy kódlap-alapú "
            f"kódolás soha nem bukik el, tehát a hibajelzést cseréled kényelemre."
        )

    @staticmethod
    def _delimiter_from_header(
        header_line: str, candidates: list[str], name: str
    ) -> tuple[str, str]:
        """Az elválasztót a FEJLÉC-SOR dönti el. Visszatér: `(elválasztó, megjegyzés)`.

        ⚠ **Ez a szabály egy bukó teszt következménye, és a lelet a
        MÉRŐESZKÖZRŐL szólt, nem a kódról.** Eredetileg a szabványkönyvtár
        felismerőjét használtuk, két hibás feltevéssel:

        1. **Feltettem, hogy hibát dob, ha nem tudja eldönteni.** Nem dob:
           *tippel* — és a tippjébe a **szóköz** is belefér. Egy elválasztó
           nélküli soron a fejléc szavakra esett szét, a betöltés „működött",
           és szemetet adott.
        2. **Feltettem, hogy a fájl egészéből dolgozhat.** A felismerő
           **sor-konzisztenciát** igényel, tehát egy cím-sor a fejléc fölött
           (nagyon gyakori valós fájlokban) megbuktatja — pedig az a sor nem is
           táblázat-sor.

        A helyettesítő szabály determinisztikus és megmagyarázható:

        - a jelöltek közül azt vesszük, amelyik a fejlécben **a legtöbbször**
          szerepel;
        - **holtverseny esetén elbukunk** — két elválasztó ugyanannyi
          előfordulással valóban eldönthetetlen;
        - ha egy másik jelölt is szerepel, azt **kimondjuk** a diagnosztikában
          (pl. a `Nettó, bruttó` fejlécnél a vessző), mert onnan derülhet ki,
          hogy mégis rosszul döntöttünk;
        - ha egyik sem szerepel, kimondott hiba — nem tippelünk.
        """
        counts = {candidate: header_line.count(candidate) for candidate in candidates}
        present = {c: n for c, n in counts.items() if n > 0}

        if not present:
            raise SourceUnreadableError(
                f"Egyetlen elválasztó-jelölt sem szerepel a fejléc-sorban: {name}. "
                f"Jelöltek: {candidates}, fejléc: {header_line[:120]!r}. Add meg a "
                f"`delimiter` beállításban — nem tippelünk."
            )

        best = max(present.values())
        winners = sorted(c for c, n in present.items() if n == best)
        if len(winners) > 1:
            raise SourceUnreadableError(
                f"Az elválasztó eldönthetetlen: {winners} mindegyike {best} "
                f"alkalommal szerepel a fejlécben ({name}). Add meg a `delimiter` "
                f"beállításban — a holtversenyt nem döntjük el találgatással."
            )

        delimiter = winners[0]
        others = sorted(c for c in present if c != delimiter)
        note = ""
        if others:
            note = (
                f"elválasztónak a(z) {delimiter!r} lett választva ({best} előfordulás "
                f"a fejlécben); a fejlécben szerepel még: "
                + ", ".join(f"{c!r}×{present[c]}" for c in others)
                + " — ha a választás rossz, itt látszik"
            )
        return delimiter, note
