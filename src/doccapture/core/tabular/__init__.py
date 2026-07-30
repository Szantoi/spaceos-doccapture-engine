"""A táblázatos út domain-oldala: séma, beállítások, érték-értelmezés.

Alcsomag, mert három külön felelősség van benne, és egy fájlban egyik sem
lenne olvasható:

| Modul | Mi a felelőssége |
|---|---|
| `options.py` | mi állítható be egy táblázat olvasásán |
| `schema.py` | fejléc-nevekből stabil belső kulcsok (illesztés) |
| `values.py` | cellából `Extracted` — itt lesz a bizonytalanság adat |

Ami itt NINCS: fájl-olvasás. Az adapter dolga (`infrastructure/tabular/`).
A határ gépi kapuval őrzött (`tests/test_core_boundary.py`).
"""

from __future__ import annotations

from doccapture.core.tabular.options import TabularOptions
from doccapture.core.tabular.schema import (
    ColumnBinding,
    ColumnSpec,
    ColumnType,
    SchemaBinding,
    TableSchema,
    normalize_header,
    split_header_unit,
)
from doccapture.core.tabular.values import interpret_cell, parse_number

__all__ = [
    "ColumnBinding",
    "ColumnSpec",
    "ColumnType",
    "SchemaBinding",
    "TableSchema",
    "TabularOptions",
    "interpret_cell",
    "normalize_header",
    "parse_number",
    "split_header_unit",
]
