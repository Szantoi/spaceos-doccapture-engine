# spaceos-doccapture-engine

> Dokumentum-befogadó motor: **Excel/CSV · digitális PDF · szkennelt kép ·
> kézírás** → normalizált javaslat, kereshető PDF, RAG-export.
>
> **Iparág-agnosztikus.** Ez a csomag nem tud semmit egyetlen iparágról,
> ügyfélről vagy cél-rendszerről sem — és ezt gépi kapu méri (`tools/neutrality_guard.py`).

## Mire való

Egy cég **integrálásakor** a meglévő tudását kell átvenni: árlisták,
cikktörzsek, partner-megnevezések, műszaki lapok, jegyzőkönyvek — vegyesen
digitális és papír alapon. Ez a motor ezt a négyféle bemenetet fogadja, és
**egyetlen normalizált javaslat-alakot** ad vissza.

## A négy bemenet — NÉGY külön út

| Bemenet | Amit teszünk | Modell kell? |
|---|---|---|
| Excel / CSV | oszlop-térképezés, típus-felismerés, validáció | **nem** — ez parse |
| Digitális PDF | a meglévő szövegréteg kiolvasása | **nem** — kész |
| Szkennelt kép / papír | raszter → szövegréteg (OCR) | részben |
| Kézírás | vizuális átirat bizonytalanság-jelzéssel | igen |

**Összemosni őket tervezési hiba:** a legolcsóbb eseteket oldanánk meg a
legdrágább úton, és modellt engednénk oda, ahol determinisztikus parse a helyes
válasz.

## A két szabály, ami a motor jellegét adja

### 1. A bizonytalanság adat, nem hiba

Minden kimenő érték **megbízhatósági szintet** hordoz: `CONFIRMED` /
`NEEDS_REVIEW` / `MISSING`. **„Inkább hiány, mint téves"** — a csendes tévedés
drágább, mint a bevallott hiány.

### 2. Olvasás ≠ döntés

A motor megmondja, **mi van a papíron**. Azt **nem**, hogy mi kerüljön a
fogadó rendszerbe — a párosítás, az átváltás és a jóváhagyás a fogyasztó
felelőssége. Ezért auditálható, ami ráépül.

## Amit a motor SOHA nem tesz

- **Nem ír a forrásba.** A bemeneti mappa csak olvasható: nincs létrehozás,
  átnevezés, törlés, másolás.
- **Nem futtat aktív tartalmat.** Makrós/aktív dokumentumnál a tárolt
  gyorsítótárat olvassa; makró, képlet, lekérdezés, külső hivatkozás **nem fut**.
  *(Biztonsági és determinizmus-kérdés egyszerre: egy futtatott képlet ma és
  holnap mást adhat.)*
- **Nem tippel.** Amit tudottan rosszul olvasunk (hosszú azonosítók, kézírás),
  az konfigurálhatóan **kikapcsolható**, és emberi kitöltésre jelölt lesz.
- **Nem normalizál mértékegységet vakon.** Az eredeti egység megőrzendő; a
  konverzió explicit és naplózott.

## Bizonyíték-lánc

Minden kinyert adat visszavezethető: **relatív forrás-útvonal + tartalom-hash
(SHA-256)**. Így egy későbbi eltérésnél eldönthető, a forrás változott-e vagy a
kinyerés. Üzleti bináris nem kerül a repóba.

## Táblázatos út — ez az egyetlen kész út (DC-01b)

A cégek integrálásának **leggyakoribb** bemenete, és ez megy elöl, mert modell
nélkül, determinisztikusan járható. Két adapter, **egy** közös domain-logika:

| Adapter | Bemenet | Külső függőség |
|---|---|---|
| `DelimitedTabularReader` | elválasztott szöveg (CSV és társai) | **nincs** |
| `WorkbookTabularReader` | munkafüzet, makró-kiterjesztéssel is | `tabular` extra |

```python
from doccapture.core.config import CaptureConfig
from doccapture.core.tabular import ColumnSpec, ColumnType, TableSchema
from doccapture.usecases.load_tabular import TabularLoader

config = CaptureConfig(input_root="/valahol/az-ugyfel-mappaja")
schema = TableSchema(
    columns=(
        ColumnSpec("kod", ("Kód", "Cikkszám"), ColumnType.TEXT, required=True),
        ColumnSpec("mennyiseg", ("Mennyiség",), ColumnType.NUMBER),
    ),
    identity_keys=("kod",),
)

record = TabularLoader(config).load("arlista.csv", schema)
record.rows[0]["kod"].value        # a BELSO kulcs, nem a fejléc szövege
record.rows[0]["kod"].confidence   # CONFIRMED / NEEDS_REVIEW / MISSING
record.needs_human                 # egyetlen bizonytalan cella is igazzá teszi
record.diagnostics                 # amit észrevettünk, de NEM javítottunk
```

**A séma adat, nem kód** (`TableSchema.from_dict()`): a mezőnevek konfiguráció,
különben minden új ügyfél forrás-módosítást igényelne.

Telepítés a munkafüzet-úthoz: `pip install "doccapture-engine[tabular]"`.
A magnak és a szöveges útnak **nincs** függősége — és ez mérve van (a CI első
köre a táblázat-olvasó **nélkül** futtatja őket).

Részletes tervezési szándék: [`docs/DESIGN-DC-01b-tablazatos-betolto.md`](docs/DESIGN-DC-01b-tablazatos-betolto.md).

## Irat-típus szerinti elemzés (DC-06)

**Két független tengely.** Az `InputKind` azt mondja meg, *hogyan olvassuk*; az
**irat-profil** azt, hogy *mi az irat, és mit kérünk tőle*. A kettő **szorzat**:
egy munkalap jöhet szkennelve és táblázatként is.

```python
from doccapture.infrastructure.profile_registry import load_profiles
from doccapture.infrastructure.text_lines import TextLineReader
from doccapture.usecases.analyze_document import DocumentAnalyzer
from doccapture.core.models import InputKind

profiles = load_profiles("profiles")            # a profil ADAT, nem kód
lines, evidence = TextLineReader(config).read("irat.txt")
record = DocumentAnalyzer(profiles, config).analyze(
    lines, input_kind=InputKind.TEXT_LAYER_DOCUMENT, evidence=evidence
)

record.fields["document_profile"]   # a felismert típus, megbízhatósággal
record.fields["job_number"]         # a profil szerinti mező, bizonyítékkal
record.diagnostics                  # az önellenőrző számtan mérlege
```

**A felismerés bizonyítékkal dönt, nem valószínűséggel** — és **holtversenynél
nem dönt**: egy téves irat-típus nem egy mezőt ront el, hanem az egész elemzést,
és sikeresnek látszik. Ezért a „nem tudom, milyen irat" **érvényes válasz**.

**Az önellenőrző számtan ingyen ellenőrzés.** A profil deklarálja az iraton
meglévő egyenlőségeket (`végösszeg = adóalap + adó`, `összes idő = ciklusidő ×
darabszám`). Ha nem áll, **jelölünk, nem javítunk** — és a diagnosztika
**megnevezi, melyik egyenlőség bomlott el**. Ha egy érték **hiányzik**, de a
többiből kiszámolható, a szabály **kitölti** — de `NEEDS_REVIEW`-val, mert egy
származtatott érték, ami megkülönböztethetetlen a leolvasottól, csendes tévedés.

⚠ **A profilok konfiguráció.** A `profiles/` alatt **semleges példák** vannak; a
konkrét mezőkészlet a fogyasztóé, és a bevezetés során **nő**. Egy iparági mező a
motorban azt jelentené, hogy a termék egyetlen iparágban használható.

Tervezési szándék: [`docs/DESIGN-DC-06-dokumentum-profilok.md`](docs/DESIGN-DC-06-dokumentum-profilok.md).

## A publikált szerződés (DC-02)

A motor kimenete **hash-pinnelt szerződés** mögött áll, hogy a fogyasztó
**a motor belsejéről ne tudjon** — és hogy a motor **cserélhető** legyen.

| Műveltár | Mi |
|---|---|
| `contracts/capture-record.schema.json` | a szerződés — **forrás-igazság**, nem melléktermék |
| `contracts/capture-record.pin.json` | SHA-256 pin, és **kimondja, mit hasheltünk** |
| `contracts/samples/*.json` | **aranypéldány a motor VALÓDI kimenetéből** |

⚠ **Ez ADAT-szerződés, nem HTTP-API.** A motor könyvtár és eszköz; futhat
in-process, soron át, vagy később HTTP mögött — **a szállítás cserélhető, az alak
nem.** Egy HTTP-API feltételezné a telepítési alakot, amit szándékosan
konfigurációnak hagytunk.

**A hash a wire-tartalmat fedi, és ezt három kapu méri** (`tests/test_contract.py`):
minden előállított mező szerepel a sémában · minden sémában deklarált mező elő is
áll · és a **származtatott** `needs_human` premisszáját **újraszámoljuk a
wire-ból**, mert egy nem ellenőrzött premissza mellett a hash arra a mezőre
megszűnne identitás lenni.

```
python tools/contract_pin.py            # ellenorzes (CI-ben ez fut)
python tools/contract_pin.py --write    # ujraszamitas -- a verzio-emeles KIMONDOTT lepes
```

⚠ **A szerződés-fájlok sorvégei nem fordulhatnak át** (`.gitattributes`:
`contracts/** -text`). A pin **bájt-szintű**, tehát egy `LF → CRLF` fordítás
elbuktatja — olyan hibával, aminek a forrása nem is a repóban van, hanem a
fejlesztő `core.autocrlf` beállításában. Külön kapu mondja ki ezt az okot, mert a
puszta pin-bukás félrevezetne.

## Elvek

**[`docs/PRINCIPLES.md`](docs/PRINCIPLES.md)** — 15 elv, éles üzemben megvett
tapasztalatból, és **minden elv mellett kiírva, hogy fedi-e gépi kapu**. Ma:
**10 teljes, 2 részleges, 3 nem fedett** — és a három nem fedett **nevesítve** van,
mert egy „elv", amit semmi nem őriz, dokumentáció, nem szabály.
*(A számot teszt köti a táblához: `tests/test_principles.py`.)*

## Mérőeszközök

```
python tools/neutrality_guard.py           # marka-, iparagi es ugyfelnev-kapu
python tools/measure_dependency_free.py    # a fuggoseg-mentesseg MERESE
python tools/mutation_check.py             # a kapuk HARAPNAK-e (10/10)
```

Mindhárom a CI-ban is fut. A második **negatív kontrollal** kezd (bizonyítja,
hogy a blokkoló fog — különben a mérés semmit nem állít), és **kimondja a
kihagyott teszteket**: egy `skipUnless`-szel csendben kimaradó modul zöld
számlálót adna, ami semmit nem mért.

## Architektúra

Hexagonális (portok és adapterek):

```
src/doccapture/
├─ core/            domain-modellek, portok, config, hibák, naplózás  — NINCS infra-import
│  ├─ tabular/      HOGYAN olvassuk: séma-illesztés, érték-értelmezés, összeállítás
│  └─ documents/    MI az irat: profil, felismerés, mező-kinyerés, önellenőrző számtan
├─ infrastructure/  adapterek + bizonyíték-lánc + profil-katalógus
└─ usecases/        a fázisok (táblázat-betöltés, irat-elemzés)
profiles/           SEMLEGES példa-profilok — adat, nem kód
tools/              mérőeszközök (semlegesség, függőség-mentesség, mutáció)
```

**A két alcsomag a két tengely**, és az érték-értelmezés **mindkettőn ugyanaz**
(`core/tabular/values.py`) — ha kettő lenne, az egyik előbb-utóbb elcsúszna.

**Az oszlop-térképezés a magban van, nem az adapterekben.** Ha az adapterekben
lenne, ugyanarról a szabályról két igazság keletkezne — és amikor a kettő
elcsúszik, az egyik csendben hazudni fog.

**Minden konfigurálható érték a config-objektumon át megy** — nincs hardcode.
A cél-rendszer, a partner-azonosítók, az adókulcsok, a mértékegységek és a
mezőnevek **mind konfiguráció**.

## Semlegességi kapu

```
python tools/neutrality_guard.py
```

CI-ben is fut. Elbukik, ha a forrásban márka-, iparági vagy ügyfélnév jelenik
meg. **Ez nem formaság:** a csomag akkor eladható, ha bármely iparágban
használható — és a semlegességet gépi kapunak kell mérnie, nem figyelemnek.

## Licenc

**MIT** — ld. [`LICENSE`](LICENSE). Azért nyílt és azért a legkevésbé súrlódó
változat, mert a cél a **széles használat**: licenc nélkül alapértelmezésben
minden jog fenntartott, tehát a fogyasztó jogszerűen nem is próbálhatná ki.

## Állapot

**A táblázatos út kész** (DC-01b): két adapter, közös domain-logika, mért
kapukkal. **A szövegréteges OLVASÁS is kész** (DC-01a): a digitális dokumentum
meglévő szövegrétege geometriával együtt kiolvasható, háromállapotú
használhatóság-verdikttel és fail-closed útválasztással. A domain-modell és a
semlegességi kapu áll. Következik a kereshető PDF **írása**, majd a felismerő és
a kézírás.

```python
from doccapture.core.config import CaptureConfig
from doccapture.usecases.read_document_text import DocumentTextReader

config = CaptureConfig(input_root="bemenet")
eredmeny = DocumentTextReader(config).read("irat.pdf")

eredmeny.lines          # olvasási sorrendben, determinisztikusan
eredmeny.pages          # lap-geometria PONTBAN, bal-felső origóval
eredmeny.evidence       # relatív út + `sha256:` tartalom-hash (M13)
eredmeny.diagnostics    # pl. összeolvadás-gyanú megnevezett indokkal (M2)
```

A szövegréteges út a `document` extrát igényli (`pip install
"doccapture-engine[document]"`); a mag és az elválasztott szöveges út továbbra
is **függőség nélkül** működik, és ezt mérés őrzi.

**Amit a motor ma NEM tud** — kimondva, hogy ne kelljen kitalálni: összevont
cellák jelzése; **raszteres bemenet** (a port áll, adapter nincs); a **kereshető
PDF írása**; a hasáb-**szétvágás** (az összeolvadás csak **jelezve** van, M2);
elforgatott lap, vertikális szöveg és RTL írásrend; egyoszlopos táblázat;
teljesítmény nagy fájlon.

A motor korábbi, éles használatban kiforrott megoldásokból általánosít. Az
átemelés elve: **mintaként, nem receptként** — ami egy konkrét rendszerre vagy
egy konkrét cégre volt szabva, az itt **konfigurációvá** válik.
