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
| Digitális PDF | a meglévő szövegréteg kiolvasása | **nem** |
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

## Architektúra

Hexagonális (portok és adapterek):

```
src/doccapture/
├─ core/            domain-modellek, portok, config, hibák  — NINCS infra-import
├─ infrastructure/  adapterek (parse, OCR, vision, PDF, tár)
└─ usecases/        a fázisok
```

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

## Állapot

**Váz.** A domain-modell és a semlegességi kapu áll; a feldolgozó fázisok
következnek.

A motor korábbi, éles használatban kiforrott megoldásokból általánosít. Az
átemelés elve: **mintaként, nem receptként** — ami egy konkrét rendszerre vagy
egy konkrét cégre volt szabva, az itt **konfigurációvá** válik.
