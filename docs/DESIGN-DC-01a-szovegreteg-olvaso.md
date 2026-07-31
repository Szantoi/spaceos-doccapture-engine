# DC-01a — Szövegréteg-olvasó geometriával (tervezői szándék)

> **Mit old meg:** a digitális dokumentum szövegrétegét — geometriával, pont
> egységben, kitöltött jobb széllel — beviszi a már meglévő elemző-láncba.
> **Modell nem kell**: ez a második legolcsóbb út a négyből.
>
> **Mit NEM old meg:** a kereshető PDF **írását** (külön szelet), a felismerést
> (raszteres út), a hasáb-**szétvágást** és a befogadó/tároló oldalt.

---

## 1. Miért ez a szelet ment először

A négy bemenet négy külön út, és ezek költsége nagyságrendekkel tér el. A
szövegréteges úthoz **egyetlen** csomag kell (6,0 MB, nulla tranzitív
függőség — mérve), a felismerő úthoz több száz megabájt és futásidejű
modell-letöltés. Egy cég integrálásakor a bemenetek jelentős része **már
digitális** — ha ezt is a felismerő úton oldanánk meg, a legolcsóbb esetet
fizetnénk meg a legdrágábban.

Ez a szelet ezért **olvasás, nem írás**: az egyetlen út, aminek ma nulla
blokkolója van.

---

## 2. A koordináta-konvenció — EGY mértékegység

| Kérdés | Döntés |
|---|---|
| Mértékegység | **mindig tipográfiai pont** (1/72 hüvelyk) |
| Origó | a lap **bal-felső** sarka, az y **lefelé** nő |
| Raszteres eredet | `PageLayout.source_dpi` — **provenancia**, nem alternatív egység |

**Miért a domainben áll a szabály, nem az adapterben:** az olvasó könyvtár
**alul-nullás** koordinátát ad (a lap aljától számol), a raszteres út
felül-nullásat. Ha a szabály az adapterben élne, a második adapter csendben
megfordítana mindent — és ez a fajta hiba nem hibaüzenetként jelenik meg, hanem
fejjel lefelé álló lapként, amit senki nem néz meg.

A „dpi **vagy** pont-alapú méret" megfogalmazást **elvetettük**: egy mező két
jelentése ugyanaz a hibaosztály, amit az opcionális jobb szélnél is elutasítunk.

### Amit az invariáns NEM fog meg — és ezt mérni kell

A `TextFragment.__post_init__` kikötése `x_left < x_right` és
`y_top < y_bottom`. Ez **két** elrontási módból **egyet** fog meg:

| Elrontás | Mit ad | Elbukik-e az invariánson |
|---|---|---|
| **név szerinti** átvétel (a natív „felső" él → `y_top`) | `y_top > y_bottom` | **igen** |
| **index szerinti** átvétel (a négyes 1. és 3. eleme) | `y_top < y_bottom`, de a lap fejjel lefelé | **nem** |

Ezért a kapu-készlet nem elégszik meg az invariánssal: a teszt a **várt
koordinátát** méri. Mérve, egy 841,89 pont magas lapon, alulról y=700-ra írt
szövegre a helyes `y_top` ≈ 133,3 — nem ≈ 699,9.

*Ez ugyanaz a tanulság, mint a megengedő teszteknél: egy feltétel, ami a hibás
alakra is teljesül, nem kapu.*

---

## 3. A háromállapotú verdikt — és a mért csapda mögötte

A szövegréteg megléte **nem** logikai kérdés. Mérve: egy szkennelt lapon, amin
csak a szkenner lábléc-bélyegzője van, a szövegréteg **25 érdemi karaktert** ad
**1 téglalapban**. Egy `van-e karakter?` boolean ezt a bélyegzőt dokumentum-
tartalomnak minősítené: a lap a szövegréteges úton menne tovább, a valódi
tartalma (a kép) pedig **csendben elveszne**.

| Verdikt | Mit jelent | A hívó teendője |
|---|---|---|
| `USABLE` | elég érdemi karakter/lap | mehet a szövegréteges úton |
| `AMBIGUOUS` | van szöveg, de kevés | **fail-closed** — kimondott hiány |
| `ABSENT` | gyakorlatilag üres | a felismerő út következik (későbbi szelet) |

A `usable` property **csak** a `USABLE`-re igaz. A két hibairány nem
egyenrangú: a kétértelműt igennek venni **csendben téves** eredményt ad, nemnek
venni **kimondott hiányt** — és „inkább hiány, mint téves" (M6).

A `has_text_layer()` a mérés verdiktjéből **származik**, nem külön küszöbből:
egy igazság ugyanarról a döntésről.

---

## 4. M2 — ami elkészült, és ami szándékosan nem

**Elkészült:** az összeolvadás **jelzése**. A lapszélesség konfigurált hányadát
átfogó fragmenst megjelöljük, megnevezett indokkal és **mért aránnyal**.

**Nem készült el:** a szétvágás. Ahol a hasábok egy futamban jönnek, a köztük
lévő rés a szövegből már **elveszett**, és az egyetlen megbízható vágópont a
horgony-token — az viszont **profil-adat** (M1). Egy elrendezés-szintű
vágó-szabály itt két igazságot teremtene ugyanarról.

Ezért az elv-tábla `részben` állapotot mutat, nem `✅`-t. A különbség nem
szőrszálhasogatás: a `✅` azt üzenné, hogy a hasábos forrás megoldott — és a
következő bevezetésnél senki nem nézné meg.

**A hamis-riasztási kontroll kötelező.** Egy detektor, ami minden lapot
megjelöl, megkülönböztethetetlen attól, amelyik nem is fut.

---

## 5. Rétegzés — mi hol lakik és miért

| Réteg | Mi | Miért nem máshol |
|---|---|---|
| mag: `layout` | geometria-típusok + invariáns | a szabály a domainé; adapterben a második adapter megfordítaná |
| mag: `text_layer_options` | domain-küszöbök | mikor *használható* egy réteg — nem könyvtár-paraméter |
| mag: `columns` | olvasási sorrend + összeolvadás-jelzés | mindkét olvasási út kéri; két példány elcsúszna |
| infra: `probe` | a réteg **mérése** | dokumentumot nyit; és önállóan futtathatónak kell lennie, mert ez az útválasztás bemenete |
| infra: `reader` | a réteg **kiolvasása** | az egyetlen hely, ahol a könyvtár neve szerepel |
| use-case | útválasztás + fail-closed döntés + sorrend | se az adapteré (nem tudja, mi a következő út), se a magé (nem nyithat fájlt) |

### Az olvasási sorrend determinizmusa

A rendezés kulcsa `(y_top, x_left, y_bottom, x_right, text)` — az utolsó kulcsok
**döntetlen esetén is** teljes rendezést adnak. A forrás-prototípus ezt modellre
bízta, amitől a sorrend futásonként változhatott, és minden későbbi lépés
nem-determinisztikus bemenetet kapott.

---

## 6. Egy határsértés, amit a kapu bevezetése hozott elő

A hexagonális határ kapuja eddig **csak importokat** vizsgált. Az `open()`
beépített függvény, a fájlkezelő modul pedig szabványkönyvtár — tehát a magban
fájlt nyitni **zöld maradt**.

A kaput ebben a szeletben kiterjesztettük fájlrendszer-hozzáférésre, és az
**azonnal megfogott egy meglévő sértést**: a konfiguráció maga mentette és
töltötte magát. A választás nem „kivétel vagy javítás" volt: egyetlen sértés
kedvéért kivétel-listát nyitni azt üzenné, hogy a kapu alkuképes.

A perzisztálás ezért átkerült az infrastruktúrába; a szerializálás **alakja**
(mit jelent egy mező, mit kell visszaalakítani) a magban maradt. A mentés
fail-closed viselkedése — az ellenőrzés a fájl megnyitása **előtt** fut, mert az
írásra nyitás már csonkolja a meglévő fájlt — változatlan, és teszt méri.

---

## 7. Amit ez a szelet NEM tud — kimondva

- **kereshető PDF írása** (külön szelet: port-változás + betűtípus-kapu kell hozzá)
- **felismerés és raszteres út** (külön szelet)
- **kézírás** — a szeletben *egyetlen* külső határátlépés sincs, tehát az
  adatvédelmi kapunak itt nincs mit őriznie; ezt kimondjuk, nem nevezzük
  teljesítettnek
- **hasáb-szétvágás** — csak a jelzés (ld. 4. pont)
- **elforgatott lap, vertikális szöveg, RTL írásrend** — egyik fixture sem fedi
- **teljesítmény-állítás** — nem mértük
- **a befogadó/tároló oldal** — licenc-blokkolón áll, és nem ennek a rétegnek
  a hatásköre
