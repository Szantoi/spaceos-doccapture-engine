"""Portok — amit a motor a külvilágtól KÉR, a külvilág nyelve nélkül.

A port a domain oldalán áll: azt írja le, mire van szükség, nem azt, hogy ki
szolgálja ki. Ezért nincs bennük egyetlen gyártó-, könyvtár- vagy
termék-név sem — ha egy port nevéből kiderül, mi van mögötte, akkor az már nem
port, hanem burkolt függőség.

Ebben a modulban NINCS infrastruktúra-import (hexagonális határ).

AMIT SZÁNDÉKOSAN NEM EMELTÜNK ÁT
--------------------------------
A forrás-prototípusban volt egy **számla-kinyerő port** a hozzá tartozó
adatszerkezetekkel. Ez ide **nem** kerül be, két okból:

1. **Ez a G1 kapu tárgya.** Két igazság van kialakulóban ugyanarról (a
   determinisztikus munkafolyamat és a prototípus portja). Amíg Gábor nem
   döntött arról, melyik a forrás-igazság, ide bemásolni azt jelentené, hogy
   a kérdést a kódba írt tényként előredöntjük.

2. **Nem is ide tartozik.** A számla-sorok értelmezése — cikkszám-párosítás,
   mennyiség-átváltás — nem az „mi van a papíron" kérdés, hanem a „mi kerüljön
   a rendszerbe". Az az iparági réteg dolga, és ott determinisztikus szabály +
   ember, nem modell.

A prototípus adatszerkezete egyébként beégetett pénznemmel és szöveges
állapot-mezővel dolgozott — mintaként tanulság, receptként hiba lett volna.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from doccapture.core.layout import PageLayout
from doccapture.core.models import CaptureRecord, Extracted


class TabularReader(ABC):
    """Táblázatos bemenet (pl. munkafüzet, elválasztott szöveg) beolvasása.

    **Modell nem kell** — ez parse. A prototípusban ez az út HIÁNYZOTT, pedig
    egy cég integrálásakor az adatok többsége már digitális: ha ezt is a
    felismerő úton oldanánk meg, a legolcsóbb esetet fizetnénk meg a legdrágábban.

    Az aktív tartalmat (makró, képlet, külső hivatkozás) az adapter NEM futtatja
    — a tárolt gyorsítótárat olvassa.
    """

    @abstractmethod
    def read_rows(self, relative_path: str) -> list[dict[str, Extracted[Any]]]:
        """Sorok beolvasása. Az érték mindig a megbízhatóságával együtt jön."""


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

    ⚠ Ennek a portnak az ADAPTERE adatvédelmi kérdés (G4): eldöntendő, hogy a
    forrás elhagyhatja-e a telepítést, vagy a fázis csak helyben futhat. A PORT
    létezése ettől független — a telepítési alak nem domain-döntés.

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
