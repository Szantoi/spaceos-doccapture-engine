# DC-06 — dokumentum-típus szerinti elemzés (tervezési szándék)

> **Kiváltó ok (Gábor, 2026-07-30):** *„A cél, hogy a gyártás során keletkező
> munkalapokat és a számlákat, más iratokat meglegyen a specifikus elemzése."*
>
> **Leállási feltétel (QUALITY §1):** a szelet akkor kész, ha egy irat-típus
> **konfigurációból** felvehető — kód módosítása nélkül —, a felismerés
> **bizonyítékkal** dönt, a típus-specifikus mezők és az **önellenőrző számtan**
> mérve működnek, és a fel nem ismert típus **kimondott hiány**, nem tipp.

---

## 1. A központi tervezési döntés: KÉT FÜGGETLEN TENGELY

A motorban eddig **egy** tengely volt: `InputKind` — *hogyan* olvassuk
(táblázat · szövegréteg · raszter · kézírás). Gábor kérése egy **másik**
tengelyről szól: *mi az irat, és mit kell kinyerni belőle*.

|  | mit mond meg | példa |
|---|---|---|
| `InputKind` | **hogyan olvassuk** | szkennelt kép → felismerés kell |
| **`DocumentProfile`** (új) | **mi az irat, és mit kérünk tőle** | munkalap → van rajta munkaszám és művelet-sorok |

**A kettő szorzat, nem összeg.** Egy munkalap jöhet szkennelve **és**
táblázatként; egy számla lehet digitális **és** papír. Ha egy tengelyre húznánk
őket (`SCANNED_WORK_ORDER`, `DIGITAL_INVOICE`, …), az esetek száma
összeszorzódna, és minden új irat-típus **négy** új ágat jelentene.

> Ez ugyanaz a hiba, mint a négy bemenetet „OCR"-nek hívni — csak fordítva:
> ott egy tengelyt akartunk összemosni, itt kettőt akarnánk összeragasztani.

## 2. A profil ADAT, nem kód — és ez a semlegesség feltétele

**A motor a MECHANIZMUST adja, a profilokat a fogyasztó.** Egy iparág-agnosztikus
motorba nem kerülhet be konkrét iparág mezőkészlete — ha bekerülne, a szótár-őr
elbuktatná, és joggal.

Ezért:

- `DocumentProfile` **betölthető szótárból/JSON-ból** (`from_dict`), ahogy a
  `TableSchema` is;
- a motor **semleges példa-profilokat** szállít a `profiles/` alatt (kétoldalú
  kereskedelmi irat · munkalap · általános irat), amikben **nincs** iparági mező;
- a konkrét ügyfél-profil **konfiguráció**, és a bevezetés során **nő** — ugyanaz
  az elv, mint a megfeleltetési táblánál (M5).

## 3. A felismerés BIZONYÍTÉKKAL dönt, nem valószínűséggel

**Nem osztályozó, nem modell.** Minden profil **horgonyokat** deklarál: olyan
token-mintákat, amiknek szerepelnie kell az iraton (M1 — *stabil azonosítóval
ismerd fel, ne névre illessz*).

A felismerés eredménye `Extracted[str]` (a profil azonosítója), és a
megbízhatóság **kimondja, mit tudunk**:

| Eset | Megbízhatóság | Miért |
|---|---|---|
| pontosan egy profil horgonyai illeszkednek | `CONFIRMED` | egyértelmű bizonyíték |
| több profil illeszkedik, de van **szigorúan legjobb** | `NEEDS_REVIEW` | döntöttünk, de az ember nézze meg |
| holtverseny két profil között | `MISSING` | **nem döntünk** — a téves típus minden mezőt elrontana |
| egy profil sem illeszkedik | `MISSING` | „nem tudom, milyen irat" **érvényes válasz** |

**Miért `MISSING` a holtverseny:** ha rossz profilt választunk, nem egy mező lesz
hibás, hanem **az egész elemzés** — és úgy fog kinézni, mint egy sikeres
feldolgozás. Ez a legdrágább néma hiba, amit ez a szelet okozhatna.

## 4. Az önellenőrző számtan: M3 és M4 együtt, deklaratívan

Az üzleti iratok tele vannak **redundanciával**, és ez **ingyen ellenőrzés**:
tétel-érték = mennyiség × egységár; adóalap × kulcs = adó; adóalap + adó =
végösszeg; művelet-idők összege = összes idő.

`ConsistencyRule` ezt **adatként** írja le (`bal = jobb ± tűrés`), és két dolgot
tud:

1. **Ellenőriz (M3).** Ha nem stimmel, **jelöl, nem javít** — és a diagnosztika
   **megnevezi, MELYIK egyenlőség bomlott el**, mert a hiba abból visszafejthető.
2. **Származtat (M4).** Ha egy érték **hiányzik**, de a többiből kiszámolható, a
   szabály kitöltheti — `NEEDS_REVIEW` megbízhatósággal, és a származtatás útja
   **kimondva** a megjegyzésben.

> **M4 a gyakorlatban:** ha a mennyiség olvasása törékeny, de az egységár és a
> tétel-érték biztos, akkor a mennyiséget **azokból** számoljuk. Nem azért, mert
> szebb, hanem mert **kevésbé érzékeny a hibára**.

⚠ **Ahol ez a szelet MEGÁLL — és ez a G1/G2 határ.** A számtan azt vizsgálja,
hogy **az irat önmagában stimmel-e**. Azt **nem**, hogy mi kerüljön a fogadó
rendszerbe: cikkszám-párosítás, mennyiség-átváltás, jóváhagyás **nincs itt**, és
nem is lesz. Az az iparági réteg dolga, determinisztikus szabállyal + emberrel.

## 5. A mezők kinyerése: címke → érték, determinisztikusan

`FieldSpec` deklarálja az **elfogadott címkéket** (konfiguráció, több változat),
a típust, a kötelezőséget és az M7-címkét. A kinyerés a szövegsorokból dolgozik:

- a címke **után** álló érték ugyanabban a sorban, vagy
- ha ott nincs, a **következő** nem üres sorban (a hasábos elrendezés miatt).

**Kétértelműség itt is hiba:** ha ugyanaz a címke több helyen szerepel eltérő
értékkel, `NEEDS_REVIEW` megy vele, és a diagnosztika **mindkét helyet** kiírja.
Ha egyetlen helyen van, de a `FieldSpec` M7-jelölt, akkor **nem olvassuk** — a
táblázatos úton már megtanultuk, miért (a forrás is romolhat).

## 6. Amit ez a szelet a QUALITY-ból pótol is

| QUALITY | Hiány a DC-01b-ben | Ebben a körben |
|---|---|---|
| §3 — *„a futó kódot loggal kell tudni nyomon követni"* | **nulla logolás** | `core/observability.py`: strukturált napló, **abszolút út és titok nélkül**, gépi kapuval |
| §5 — *„ami bevált, paraméterezhető szkript"* | a mérő-szkriptek eldobható mappában | `tools/mutation_check.py` + `tools/measure_dependency_free.py`, **konfigurációval** |
| §4 — *„az eredményt össze kell vetni az elvárásokkal"* | szám volt, összevetés nem | a task-fájlban tételes elvárás ⇄ eredmény tábla |

**A naplózásról külön, mert ez biztonsági kérdés is:** egy napló, ami kiírja a
forrás **abszolút útvonalát**, felfedi a gépi könyvtárszerkezetet; ami kiírja egy
mező **értékét**, üzleti adatot szivárogtat egy log-fájlba. Ezért a napló
**relatív utat** és **darabszámot** ír, értéket nem — és ezt **teszt őrzi**, nem
figyelem.

## 7. Amit szándékosan NEM építünk ebben a szeletben

- **Nincs osztályozó modell.** A típus-felismerés horgony-alapú. Egy modell itt
  ugyanaz a hiba lenne, mint LLM-mel tippelni cikkszámot: nem auditálható.
- **Nincs táblázat-szerkezet felismerés képből.** A művelet-sorok/tétel-sorok
  kinyerése raszterből a DC-01 tárgya; ez a szelet a **szövegsorokból** dolgozik,
  bárhonnan jöttek.
- **Nincs iparági profil.** A `profiles/` példák semlegesek; a konkrét
  mezőkészlet a fogyasztóé.
- **Nincs jóváhagyási hurok.** Az a DC-04, és a G3 szerint portál-UI.

## 8. Amit előre kimondunk: mit NEM fog tudni

1. **A címke→érték kinyerés egysoros/kétsoros esetet fed.** Táblázatos
   elrendezésben, ahol a címke egy oszlop-fejléc és az érték három sorral lejjebb
   van, **nem fog találni** — ott a táblázatos út a helyes eszköz.
2. **A horgony-alapú felismerés ott bukik, ahol a horgony sérült** (rossz
   felismerés, hiányzó bélyegző). Ilyenkor `MISSING` jön, ami helyes válasz — de
   azt jelenti, hogy **emberi besorolás kell**.
3. **A számtani szabályok csak azt tudják, amit deklaráltunk.** Egy iraton, ahol
   nincs redundancia, ez a réteg **nem ad ellenőrzést** — és ezt ki kell mondani,
   nem „ellenőrzöttnek" nevezni.
