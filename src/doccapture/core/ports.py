"""Portok — amit a motor a külvilágtól KÉR, a külvilág nyelve nélkül.

A port a domain oldalán áll: azt írja le, mire van szükség, nem azt, hogy ki
szolgálja ki. Ezért nincs bennük egyetlen gyártó-, könyvtár- vagy
termék-név sem — ha egy port nevéből kiderül, mi van mögötte, akkor az már nem
port, hanem burkolt függőség.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).

AMIT SZÁNDÉKOSAN NEM EMELTÜNK ÁT — ÉS AMI MÁR NEM IS FOG BEKERÜLNI
------------------------------------------------------------------
A forrás-prototípusban volt egy **számla-kinyerő port** a hozzá tartozó
adatszerkezetekkel. Ez ide **nem** kerül be, és ez már nem nyitott kérdés:

**G1 ELDÖNTVE (Gábor, 2026-07-30): a bevételezés a gazda.** A számla-értelmezés
az iparági rétegé (a bevételezési repó); a motor **bemenet-előkészítő** marad —
sorokat, táblákat és szövegréteget ad, nem számla-jelentést. Két igazság volt
kialakulóban ugyanarról, és ez a döntés zárja: **egy** gazda van.

Miért ez a helyes határ, a döntéstől függetlenül is: a számla-sorok értelmezése
— cikkszám-párosítás, mennyiség-átváltás — nem az „mi van a papíron" kérdés,
hanem a „mi kerüljön a rendszerbe". Az utóbbi determinisztikus szabály + ember,
nem modell, és **auditálható** kell hogy legyen.

A `tests/test_ports.py` gépi kapuja ezért **véglegesen** marad: ha egyszer
elbukik, az nem hiba, hanem jelzés, hogy valaki a határon átlépett.

A prototípus adatszerkezete egyébként beégetett pénznemmel és szöveges
állapot-mezővel dolgozott — mintaként tanulság, receptként hiba lett volna.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from doccapture.core.layout import PageLayout
from doccapture.core.models import CaptureRecord, Extracted
from doccapture.core.tabular.result import TabularReadResult
from doccapture.core.tabular.schema import TableSchema


class TabularReader(ABC):
    """Táblázatos bemenet (pl. munkafüzet, elválasztott szöveg) beolvasása.

    **Modell nem kell** — ez parse. A prototípusban ez az út HIÁNYZOTT, pedig
    egy cég integrálásakor az adatok többsége már digitális: ha ezt is a
    felismerő úton oldanánk meg, a legolcsóbb esetet fizetnénk meg a legdrágábban.

    Az aktív tartalmat (makró, képlet, lekérdezés, külső hivatkozás) az adapter
    **NEM futtatja** — a tárolt gyorsítótárat olvassa (M11). Ez egyszerre
    biztonsági és determinizmus-kérdés: egy futtatott képlet ma és holnap mást
    adhat.
    """

    @abstractmethod
    def read(self, relative_path: str, schema: TableSchema) -> TabularReadResult:
        """Egy táblázat beolvasása a megadott séma szerint.

        A **séma paraméter**, nem konstruktor-adat: egy adapter ugyanabban a
        bevezetésben több különböző táblát olvas (árlista, cikktörzs,
        beszállítói lista), és mindegyiknek más az alakja.

        Az érték mindig a megbízhatóságával együtt jön; üres cella `MISSING`,
        azaz **adat**, nem kivétel. Kivétel csak akkor, ha magát a forrást vagy
        a fejlécet nem tudtuk értelmezni.
        """


class TextLayerReader(ABC):
    """Beágyazott szövegréteg kiolvasása dokumentumból. **Modell nem kell.**"""

    @abstractmethod
    def has_text_layer(self, relative_path: str) -> bool:
        """Van-e használható szövegréteg.

        Ez dönti el, hogy a dokumentum a szövegréteges vagy a raszteres úton
        megy tovább — a kiterjesztés erre nem elég.
        """

    @abstractmethod
    def read_pages(self, relative_path: str) -> list[PageLayout]:
        """A meglévő szövegréteg kiolvasása, elrendezéssel együtt."""


class RasterTextReader(ABC):
    """Raszteres kép szövegrétegének előállítása (felismerés)."""

    @abstractmethod
    def read_page(self, relative_path: str) -> PageLayout:
        """Egy lap felismerése. A darabok nyers megbízhatóságot hordoznak."""


class HandwritingTranscriber(ABC):
    """Kézírás vizuális átirata — MINDIG bizonytalanság-jelzéssel.

    Külön port, nem a felismerő egyik módja: a kézírás a negyedik út, más a
    hibaprofilja, és más a helyes viselkedés is (itt a hiány gyakran jobb
    válasz, mint a tipp).
    """

    @abstractmethod
    def transcribe(self, relative_path: str) -> Extracted[str]:
        """Átirat a megbízhatóságával. Bizonytalanságnál `NEEDS_REVIEW` vagy `MISSING`."""


class VisualAssistant(ABC):
    """Vizuális megértést igénylő segédkérdés a forrás egy darabjára.

    **G4 ELDÖNTVE (Gábor, 2026-07-30): helyi alap, külső opcionális.** A
    modellt igénylő fázis alapértelmezésben **a telepítésen belül** fut; külső
    szolgáltatóhoz a forrás CSAK akkor kerülhet, ha a config ezt kimondottan
    engedi (`allow_external_processing`), és akkor is **naplózva**.

    A kaput a `CaptureConfig.assert_external_processing_allowed()` adja, és
    minden olyan adapternek meg kell hívnia, ami a forrást kiengedi a
    telepítésből. A port létezése ettől független — a telepítési alak nem
    domain-döntés, de a **határátlépés engedélye** az.

    Termékként ez a döntés két piacot nyit egy kódbázison: van „az adatai nem
    hagyják el a telephelyet" változat, és van felhő-alapú — a különbség
    **konfiguráció**, nem külön termék.

    A motor ezt CSAK olvasásra használja („mi van a papíron"). Arra soha, hogy
    mi kerüljön a fogadó rendszerbe.
    """

    @abstractmethod
    def describe(self, relative_path: str, question: str) -> Extracted[str]:
        """Válasz a megbízhatóságával együtt."""


class SearchableDocumentBuilder(ABC):
    """Kereshető dokumentum előállítása láthatatlan szövegréteggel.

    Az eredetit nem bántjuk: a kimenet másolat, és **visszavezet a forrásra**.
    """

    @abstractmethod
    def build(self, pages: list[PageLayout], output_path: str) -> None: ...


class CaptureRecordStore(ABC):
    """A kinyert rekordok tárolása és visszaolvasása.

    A mentés legyen atomikus, és párhuzamos írásnál zárral védett — a
    prototípusban ez drágán megtanult tapasztalat volt.
    """

    @abstractmethod
    def save(self, records: list[CaptureRecord]) -> None: ...

    @abstractmethod
    def load(self) -> list[CaptureRecord]: ...


@dataclass(frozen=True)
class IndexMatch:
    """Egy találat a keresésből."""

    chunk_id: str
    content: str
    score: float
    metadata: dict[str, Any]


class SearchIndex(ABC):
    """Kereshető index a kinyert tartalom fölött."""

    @abstractmethod
    def add(self, chunks: list[dict[str, Any]]) -> None:
        """chunk: {"id": str, "content": str, "metadata": dict}"""

    @abstractmethod
    def search(
        self,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[dict[str, Any]] = None,
    ) -> list[IndexMatch]: ...

    @abstractmethod
    def remove_document(self, document_id: str) -> None: ...

    @abstractmethod
    def count(self) -> int: ...
