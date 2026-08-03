"""Szállított erőforrások — ma: a beágyazandó betűtípus és a licence.

MIÉRT CSOMAGON BELÜL
--------------------
A kereshető PDF **beágyazott** betűtípust igényel, és a motor **könyvtárként is
használható**: aki `pip install`-lal kapja meg, annak a betűtípus **vele kell
hogy jöjjön** — különben a termék a telepítés után némán rossz kimenetet adna.
Egy repó-gyökérben álló `fonts/` mappa **nem jut el a fogyasztóhoz** (ugyanaz a
tanulság, mint a `LICENSE`-nél: egy fájl a repóban nem csomag-metaadat).

Az elérés **`importlib.resources`**-szel megy, nem `__file__`-alapú útépítéssel:
az utóbbi zip-importnál és szerkeszthető telepítésnél elszáll, és a hibája
**telepítés-függő** lenne — pontosan az a hibaosztály, amit ebben a repóban
kétszer is drágán tanultunk meg.

MIT NEM CSINÁL EZ A MODUL
-------------------------
**Nem olvassa be a betűtípust.** A `core/` határ-kapuja (K8) tiltja a
fájlrendszer-hozzáférést a magban, és ez a modul a mag alatt áll: itt csak az
**azonosítók** vannak, a beolvasás az adapteré.
"""

from __future__ import annotations

# A szallitott betutipus fajlneve. EGY helyen all: a kapu, a proveniencia-doksi
# es a leendo adapter is INNEN veszi -- ket helyen allo nev ket igazsag lenne
# ugyanarrol, es az egyik elobb-utobb elcsuszna.
EMBEDDED_FONT_FILENAME = "LiberationSans-Regular.ttf"

# A betutipus licence, amit az OFL-1.1 szerint TOVABB KELL ADNI a fonttal egyutt.
EMBEDDED_FONT_LICENSE_FILENAME = "LICENSE-LiberationSans.txt"
