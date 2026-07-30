# DC-01b — a táblázatos betöltő tervezési szándéka

> Ez a dokumentum azt írja le, **mit** építettünk és **miért éppen így** — nem
> azt, hogy hogyan használjuk (az a `README.md` és a docstringek dolga).
> A QUALITY §2 miatt létezik: a design intent önmagában is termék, mert a
> következő fejlesztő a *miértet* nem tudja visszafejteni a kódból.

## Miért ez a szelet megy elöl

Egy cég integrálásakor az adatok **többsége már digitális**: árlista,
cikktörzs, beszállítói lista táblázatban. Ez az út **modell nélkül**,
determinisztikusan járható — tehát ez a leggyorsabb megtérülés és a
legkisebb kockázat. Ha a felismerő úttal kezdenénk, a látványosabb felét
építenénk előbb, és a legolcsóbb esetet fizetnénk meg a legdrágábban.

**A G-kapuktól független.** A G4 (adatvédelem) a modellt igénylő fázis
telepítési alakját dönti el; ebben a szeletben **nulla modell-hívás van**,
tehát a kapu válasza a kódját nem változtatja meg. Ezt ki kell mondani, mert
korábban a szelet „G4-re vár" címkét kapott — az a besorolás pontatlan volt.

## Amit a forrás-prototípusból átemeltünk — és amit nem

A prototípus táblázat-olvasása így nézett ki (a lényeg, tömörítve —
**a mező- és rendszernevek semlegesítve**, mert ez a repó iparág-agnosztikus,
és a cél-rendszer neve konfiguráció, nem irodalom):

```python
wb = olvaso.load_workbook(MEGFELELTETES_XLSX, data_only=True)
ws = wb.active
for r in range(2, ws.max_row + 1):
    leiras   = ws.cell(r, 2).value   # beégetett oszlop-index
    cel_kod  = ws.cell(r, 4).value   # beégetett oszlop-index
    if leiras:                       # néma sor-eldobás
        rows.append((str(leiras), cel_kod))
```

> A semlegesítés nem kozmetika: az első változatban a rendszer neve szó szerint
> bekerült ebbe a dokumentumba, és a **semlegességi kapu bukott el rajta**.
> A kapu ott fogott, ahol nem is a kódot néztem — és jól tette.

### ⚠ Utólagos javítás: a prototípusban KÉT igazság volt erre

Ez a szakasz eredetileg azt állította, hogy „a prototípus beégetett oszlop-indexet
használ". **Ez csak az egyik fájljára igaz.** A tételes felmérés (2026-07-30)
kimutatta, hogy a **fejlettebb**, hatszor nagyobb fájl már **fejléc-alias szerint**
oldja fel az oszlopokat — vagyis azt csinálta, amit itt „általánosításként" írtam le.

**Feltettem, hogy a prototípus egységes.** Nem volt az. A kisebb fájl beégetett
indexet használt, a nagyobb fejlécet — **két igazság ugyanarról**, ugyanabban a
projektben.

**Amiben a mi változatunk mégis javítás, és ez a lényegesebb rész:** a prototípus
fejléc-feloldása **csendben visszaesik egy beégetett indexre**, ha nem talál
egyező fejlécet (`index vagy alapértelmezett_index`). Vagyis egy átnevezett vagy
hiányzó fejléc nem bukik el, hanem **rossz oszlopból tölt** — pontosan az a néma
hiba, ami ellen a D2 döntés (a kétértelműség hiba, nem választás) szól. Ez
ugyanaz a minta, mint a titok-kezelésben a `környezeti_változó || '<literál>'`
fallback: **néma visszaesés a rosszabb forrásra.**

A mi implementációnk kötelező oszlopnál **elbukik**, nem kötelezőnél **kimondja**
a hiányt. A különbség nem a fejléc-illesztés léte, hanem hogy **mi történik,
amikor nem sikerül**.

**Egy dolgot jól csinált, és azt átvettük:** `data_only=True`. Ez a tárolt
gyorsítótárat olvassa, nem futtat képletet — pontosan az M11 szabály, még ha
nem is így hívta.

**Öt dolgot általánosítanunk kellett**, mert mind az öt egyetlen ügyfél
egyetlen fájljára volt szabva:

| A prototípusban | Miért nem vihető tovább | Amivé lett |
|---|---|---|
| `ws.cell(r, 2)` — beégetett oszlop-index | egy beszúrt oszlop csendben elrontja az egész betöltést, és a hiba **később** derül ki, más adaton | fejléc-név szerinti illesztés, a névlista **konfiguráció** |
| `range(2, …)` — a fejléc az 1. sor | valós fájlokban van címsor, üres sor, egység-sor a fejléc alatt | `header_row` + `data_starts_after_header`, mindkettő config |
| `wb.active` | egy munkafüzet több lapja közül a rossz is lehet aktív, és az **mentéskor változik** | `sheet_name`, `""` = aktív lap, kimondva |
| `str(desc)` | típus-információ elvesztése; a `1.23457E+15` is „szöveg" lesz | oszlop-típus + értelmezés, kétértelműségnél **hiány** |
| `if desc:` — néma sor-eldobás | nem tudod meg, hogy 40 sort dobtál el vagy 0-t | `identity_keys` + **megszámolt** kihagyás a diagnosztikában |

## A hét tervezési döntés

### D1. Az oszlop-térképezés a MAGBAN van, nem az adapterben

Két adapter van (elválasztott szöveg és munkafüzet), és lesz több. Ha a
fejléc-illesztés az adapterben lenne, **két igazság** keletkezne ugyanarról a
szabályról — és a platformon ma ez a leggyakoribb hibánk. Az adapter dolga
annyi, hogy **cellákat ad**; hogy azokból mi lesz, az domain-döntés.

Mérhető következménye: a legértékesebb logika (illesztés + értelmezés)
**infrastruktúra nélkül** tesztelhető, és a két adapter tesztje már csak azt
méri, hogy jól adja-e a cellákat.

### D2. A kétértelmű fejléc HIBA, nem választás

Ha két oszlop is illik ugyanarra a specifikációra, a betöltés **elbukik**.
A csábító alternatíva („vedd az elsőt") a legrosszabb: működni fog, és
**hónapokig** nem tudod meg, hogy a rossz oszlopból tölt.

Ugyanígy hiba, ha két különböző specifikáció **ugyanarra** az oszlopra illik.

**Ezért van kikapcsolva alapból az ékezet-hajtogatás** a fejléc-illesztésben:
az összevonás két különböző fejlécet egybe olvaszthat, és abból pont
kétértelműség lesz. Aki kéri, bekapcsolhatja — de akkor tudja, mit vállal.

### D3. A számformátum kétértelműsége HIÁNY, nem tipp

`"1,234"` lehet ezerkétszázharmincnégy és lehet egy egész kettőszázharmincnégy
ezred. **Nincs olyan szabály, ami ezt locale nélkül eldönti** — ezért nem is
találunk ki egyet:

- ha a szövegben **mindkét** jel szerepel (`.` és `,`), az **utolsó** a
  tizedesjel, a másik csoport-jel: ez univerzális, nem locale-függő;
- ha csak az egyik szerepel, **egyszer**, és **pontosan 3 számjegy** követi,
  és az egész rész 1-3 számjegy → **kétértelmű → `MISSING`**, indokkal;
- minden más eset egyértelmű (több előfordulás → csoport-jel; nem 3 számjegy
  utána → tizedesjel).

Ha a config **megnevezi** a tizedesjelet, a kétértelműség eltűnik. Az
alapértelmezés szándékosan `""` = „nincs megadva" — nem „angol" és nem
„magyar". Egy beégetett locale itt ugyanaz a hiba lenne, mint egy beégetett
cégnév.

**Csoport-jelként alapból csak olyan karakterek szerepelnek, amik egyetlen
írásrendszerben sem tizedesjelek** (szóköz, törhetetlen szóköz, keskeny
szóköz, aposztróf). A `.` és a `,` szándékosan **nincs** köztük — azokat a
fenti kétértelműség-szabály kezeli.

### D4. A képlet gyorsítótár nélkül nem „üres cella"

Ez a szelet legdrágább leletje, és a prototípus csendben elvétette volna.

`data_only=True` mellett a képlet-cella a **tárolt** értékét adja. Ha a fájlt
soha nem mentette ki táblázatkezelő (gépi generálás, vagy a képletet utólag
írták bele), akkor **nincs tárolt érték**, és az olvasó `None`-t ad — ami
megkülönböztethetetlen az üres cellától.

Vagyis: `str(None)` → `"None"`, vagy „ez a sor üres" → **néma adatvesztés**.

**A megoldás:** a munkafüzet-adapter a fájlt **kétszer** nyitja meg — egyszer
gyorsítótár-módban, egyszer képlet-módban —, és ha a gyorsítótár üres, de a
cellában képlet áll, akkor az eredmény `MISSING` **kimondott indokkal**, nem
üres cella. A képletet **nem futtatjuk ki** (M11): egy futtatott képlet ma és
holnap mást adhat, tehát a determinizmus is elveszne.

### D5. A mértékegység nem vész el, de nem is normalizálunk

Ha a fejléc egységet hordoz (`"Mennyiség (m2)"`), az egység **adattá** válik:
a rekord `unit:<kulcs>` mezőjében jelenik meg, a fejléc-cella bizonyítékával
együtt. A számot **nem** konvertáljuk (M15) — a konverzió a fogyasztó
explicit, naplózott döntése.

Ez az import-discovery terminál élő tapasztalatából jön: *„mértékegységet nem
szabad feltételezni"*. Egy cm-ben vezetett méretlap mm-ként értelmezve nem
hibás adatot ad, hanem **tízszeresen** hibásat, és semmi nem jelzi.

### D6. A táblázatos forrás NEM automatikusan megbízható

Csábító feltevés, hogy ami digitális, az pontos. Két helyen nem az:

1. **A táblázatkezelő tudományos alakra hozza a hosszú azonosítókat.** Egy
   16 jegyű vonalkód `1.23457E+15`-ként tárolódik, és az **eredeti számjegyek
   véglegesen elvesznek**. Ha ilyet látunk szöveges oszlopban, `NEEDS_REVIEW`
   megy vele — nem azért, mert az olvasás bizonytalan, hanem mert **a forrás**
   már romlott.
2. **Az M7 (emberi kitöltésre jelölt mezőtípusok) itt is érvényes.** Ez
   először ellentmondásnak tűnt: minek jelölni emberi kitöltésre egy mezőt,
   amit hibátlanul kiolvasunk egy táblázatból? Az 1. pont a válasz — épp a
   táblázat az a hely, ahol egy hosszú azonosító **magabiztosan rossz** lesz.

### D7. A port alakja hipotézis volt — az első adapter megmérte

A DC-00 kimondta, hogy a portoknak **nincs adapterük**, tehát a
használhatóságuk bizonyítatlan. Az első adapter megépítése ezt megmérte, és
**a port szűk volt**: a `read_rows()` csak sorokat adott vissza, tehát az
adapternek **el kellett volna dobnia** az illesztetlen fejléceket, a kihagyott
üres sorok számát, a felismert mértékegységeket és a gyorsítótár-hiányt.

Egy port, ami a diagnosztika eldobására kényszerít, **csendes adatvesztést
tervez be**. Ezért a port `read(relative_path, schema) -> TabularReadResult`
alakra változott. Két dolgot tanít:

- **A séma paraméter, nem konstruktor-adat**: egy adapter több különböző
  táblát olvas ugyanabban a bevezetésben.
- **A visszatérési típus a diagnosztikát is hordozza**: ha nincs hova írni,
  akkor nem lesz megírva.

## Amit NEM mértünk — kimondva

1. **Valódi ügyfél-fájlon nem futott.** A tesztek szintetikus munkafüzeteket
   és szövegfájlokat használnak, amiket magunk állítottunk elő. Egy éles
   táblázat összevont celláktól, rejtett soroktól és tagolástól más lehet.
2. **Összevont cella (`merged`) kezelése nincs.** Az olvasó a bal-felső cella
   értékét látja, a többit üresnek — ma ezt **nem jelezzük**. Ez ismert rés,
   nem lefedett eset.
3. **A `.xlsm` úton csak azt mértük, hogy a makrós fájl olvasható és nem
   futtatunk semmit.** Azt nem, hogy egy Power Query-vel vagy külső
   hivatkozással teli munkafüzet gyorsítótára mennyire friss — az a fájl
   utolsó mentésének kérdése, és a mi oldalunkról nem eldönthető.
4. **Nagy fájl teljesítménye nincs mérve.** A kétszeri megnyitás (D4) a
   memóriaigényt megduplázza; a `max_rows` korlát ezért létezik, de a
   határértéket nem méréssel állítottuk be.
5. **Az elválasztó-felismerés** a szabványkönyvtár heurisztikáját használja.
   Egyetlen oszlopú fájlon vagy szokatlan elválasztónál elbukhat — ilyenkor
   **kimondott hibát** dob, nem tippel. A felismerés pontosságát nem mértük
   sokféle valós fájlon.
