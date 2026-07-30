"""Táblázatos adapterek — a `TabularReader` port megvalósításai.

| Adapter | Bemenet | Külső függőség |
|---|---|---|
| `DelimitedTabularReader` | elválasztott szöveg (CSV és társai) | **nincs** |
| `WorkbookTabularReader` | munkafüzet (makrós fájlt is olvas, nem futtat) | `tabular` extra |

Mindkettő UGYANAZT a mag-logikát használja az illesztésre és az értelmezésre
(`core.tabular.assembly`) — így az oszlop-térképezésről nem lehet két igazság.
"""

from __future__ import annotations

from doccapture.infrastructure.tabular.delimited import DelimitedTabularReader
from doccapture.infrastructure.tabular.workbook import WorkbookTabularReader

__all__ = ["DelimitedTabularReader", "WorkbookTabularReader"]
