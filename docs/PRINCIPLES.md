# A motor elvei — drágán megvett tapasztalatok, nem ötletek

> **Miért van ez a fájl a motor repójában, és nem csak a platform tudástárában:**
> ez a csomag **önállóan eladható**. Aki csak ezt kapja meg, annak is látnia kell,
> **miért** így viselkedik a kód — különben az első „kényelmi" módosítás
> visszacsinálja azt, amit ezek az elvek megvédenek.
>
> ⚠ **Általános mintaként tanuld meg, ne receptként.** Ezek az elvek egy konkrét
> cég konkrét rendszerén, éles üzemben derültek ki. **A cél-rendszer, a cégnevek,
> az azonosítók, az adókulcsok, a mértékegységek és a mezőnevek mind
> KONFIGURÁCIÓ.** Ha bármelyik a kódba kerül, a termék egyetlen ügyfélnél
> használható.

---

## A három szabály, ami minden döntést eldönt

### 1. A négy bemenet NÉGY külön út — összemosni tervezési hiba

| Bemenet | Amire szükség van | Modell kell? |
|---|---|---|
| táblázatos fájl | oszlop-térképezés, típus, validáció | **nem** — ez parse |
| beágyazott szövegréteg | a meglévő szöveg kiolvasása | **nem** |
| raszteres kép | szövegréteg előállítása (felismerés) | részben |
| kézírás | vizuális átirat bizonytalanság-jelzéssel | igen |

Ha mind a négyet „felismerésnek" hívjuk, a **legolcsóbb** eseteket a
**legdrágább** úton oldjuk meg, és **modellt engedünk oda, ahol determinisztikus
parse a helyes válasz**.

> **És egy második tengely, ami ettől FÜGGETLEN:** *hogyan olvassuk* (a fenti
> négy út) ≠ *mi az irat, és mit kérünk tőle* (irat-profil). A kettő **szorzat**:
> egy munkalap jöhet szkennelve és táblázatként is. Ha egy tengelyre húznánk
> őket, minden új irat-típus négy új ágat jelentene.

### 2. A modell az OLVASÁSHOZ, determinisztikus szabály a DÖNTÉSHEZ

A modell abban segít, *mi van a papíron*. Abban **nem**, hogy *mi kerüljön a
fogadó rendszerbe*: a kód-párosítás, a mennyiség-átváltás és a jóváhagyás marad
**szabály + ember**.

**Egy modell-tipp nem auditálható; egy megfeleltetési tábla sora igen.**
Termékként ez **eladási érv**, nem korlát: a vevő könyvelése auditálható marad.

### 3. A jóváhagyási hurok a termék magja — nem a felismerés, és nem a felület

A **mechanika** a lényeg: a rendszer **javasol**, az ember **egy mozdulattal**
jóváhagy, és a megfeleltetési tábla **nő**. Ettől alig változik a napi rutin — és
ez a bevezethetőség kulcsa.

⚠ **A felület cserélhető, a mechanika nem.** Ha a jóváhagyás több lépésből áll,
mint eddig, az a szabály megsértése, nem a szabály fejlesztése — és ezt **meg kell
mérni**, nem érezni.

---

## A minta-készlet — és hogy mit MÉR belőle gépi kapu

A „gépi kapu" oszlop a lényeg: **egy elv, amit nem mér senki, előbb-utóbb
megsérül** — és pont az ilyen sérülés marad csendben, mert a kód tovább működik.

| # | Elv | Gépi kapu ma |
|---|---|---|
| **M1** | **Horgony-fél és ellenfél.** Egy kétoldalú iraton az egyik fél állandó (mi vagyunk), a másik változó. A horgonyt **stabil azonosítóval** ismerd fel (adószám, regisztrációs szám — konfigurációból). **Ne névre illessz:** a név elírható, az azonosító nem. | részben — a profil-horgony **kötelező**, horgony nélküli profil elbukik |
| **M2** | **Összeolvadó oszlopok.** Hasábos elrendezésnél a szövegréteg gyakran **egy sorba olvasztja** a két hasábot. A megoldás nem jobb felismerés, hanem **vágás a horgony-tokennél**. | ⚠ **nincs** — a hasáb-szétvágás nincs megírva (DC-01) |
| **M3** | **Redundancia = ingyen ellenőrzés.** Az üzleti iratok tele vannak önellenőrző számtannal. Ha nem stimmel (tűréssel), **jelöld — ne javítsd csendben**. *A hiba visszafejthető abból, melyik egyenlőség bomlik el.* | ✅ `ConsistencyRule` + mutáció |
| **M4** | **Válaszd a hibára legkevésbé érzékeny bemenetet.** Ha egy érték több úton is kiszámolható, azt az utat vedd, amelyik **nem függ a törékeny mezőtől**. | ✅ származtatás, és a származtatott érték **soha nem `CONFIRMED`** |
| **M5** | **Növekvő megfeleltetési tábla.** A külső fél a **saját szavaival** ír, mi a **saját kódjainkkal** dolgozunk. A kettő közé tábla kell, ami a **jóváhagyásból nő**. | részben — a séma/profil **adat**, körútja mérve; a tábla növése a fogyasztóé |
| **M6** | **A bizonytalanság adat, nem hiba.** Minden érték hordozzon megbízhatósági szintet. *„Inkább hiány, mint téves"* — a csendes tévedés drágább, mint a bevallott hiány. | ✅ `Extracted` invariáns + a kétértelmű szám hiánya |
| **M7** | **Amit tudottan rosszul olvasunk, azt ne olvassuk gépileg.** Kapcsold ki és jelöld emberi kitöltésre — **mezőtípusonként konfigurálva**, ne beégetett tiltással. | ✅ `human_only_field_types`, táblázatos és irat-úton is |
| **M8** | **Az eredetit nem bántjuk.** Átnevezés, szétbontás, normalizálás **másolaton**; a forrás érintetlen, a kimenet **visszavezet rá**. | ✅ mappa-pillanatkép a betöltés előtt és után |
| **M9** | **A felhasználó felülete a forrás-igazság.** Ahol az ember jóváhagy, az a hely dönt. A formátum cserélhető, a **szerepe** nem. | ⚠ **nincs** — a jóváhagyó felület nincs megírva (DC-04) |
| **M10** | **A forrás csak olvasható.** Nincs létrehozás, átnevezés, törlés, másolás. Az importáló **olvas és javasol**, nem rendez. | ✅ mérve (pillanatkép + a fájl mozgathatósága a betöltés után) |
| **M11** | **Aktív tartalmat nem futtatunk.** Makrós/aktív dokumentumnál a **tárolt gyorsítótárat** olvassuk; makró, képlet, lekérdezés, külső hivatkozás **nem fut**. Egyszerre biztonsági és **determinizmus**-kérdés: egy futtatott képlet ma és holnap mást adhat. | ✅ **injektált, szándékosan hibás gyorsítótár-érték** bizonyítja, hogy nem értékelünk ki |
| **M12** | **Zaj-fájlokat ki kell zárni.** Biztonsági másolat, lock- és gyorsítótár-fájl. A kizárási lista **konfiguráció**, mert rendszerenként más. | ✅ `excluded_name_patterns` + mérve, hogy a zaj-fájlt nem is olvassuk |
| **M13** | **Bizonyíték-lánc: relatív út + tartalom-hash.** Egy későbbi eltérésnél így eldönthető, **a forrás változott-e vagy a kinyerés**. Üzleti bináris nem kerül a repóba. | ✅ `SourceEvidence` + `sha256:` előtag; abszolút út **kapuval** tiltva |
| **M14** | **Egy munka-azonosító = egy entitás.** Az összevonás **nem** történhet gyengébb egyezés alapján. A hamis összevonás **visszafordíthatatlan**. | ⚠ **nincs** — a motor nem von össze entitást; ez a fogyasztó felelőssége |
| **M15** | **Az egységet előbb megőrizzük**, a konverzió **explicit és naplózott**. Amíg nem tudjuk biztosan az eredeti mértékegységet, ne normalizáljunk. | ✅ a fejlécből felismert egység **adat** bizonyítékkal; átváltás nincs |

**Mérve: 10 elvet fed gépi kapu, 2-t részben, 3-at egyáltalán nem** (M2, M9,
M14). A nem fedett három **nem elfelejtett**, hanem olyan réteghez tartozik, ami
még nincs megírva — és ezt jobb kimondani, mint „elvnek" nevezni valamit, amit
semmi nem őriz.

> ⚠ **Ez a három szám kapuval kötött a fenti táblához** (`tests/test_principles.py`).
> Az első leírásnál elszámoltam (9/3/3 helyett 10/2/3), és pontosan ez a fajta
> szám az, ami észrevétlenül elcsúszik: a tábla nő, az összegzés marad. Egy
> dokumentumban álló szám, amit nem mér senki, **állítás, nem mérés.**

---

## A motor fegyelme — amit a kód szintjén tartunk

- **Hexagonális határ:** a magban (`core/`) **nincs** infrastruktúra-import.
  *Gépi kapu:* `tests/test_core_boundary.py`, és **belát az alcsomagokba is**
  (`rglob`, nem `glob` — ezt egy önaudit hozta elő).
- **Minden konfigurálható érték egy helyen**, a config-objektumon át. Beégetett
  ország, nyelv, pénznem és **tizedesjel** nincs: az üres alapérték azt jelenti,
  hogy „nincs megadva", nem azt, hogy „magyar".
- **Titok soha nem kerül a configba** — csak a környezeti változó **neve**.
  *Gépi kapu:* `assert_no_secret_values`, és **`vars()`-on** iterál, nem
  `asdict()`-en, mert az utóbbi csak a deklarált mezőket látja.
- **A napló szerkezetről és darabszámról beszél, nem tartalomról.** Sem titok,
  sem **abszolút útvonal** nem kerül ki. *Gépi kapu:* `tests/test_observability.py`,
  és a **valódi** napló-hívásokat is méri, nem csak a kaput.
- **Szálbiztonság:** párhuzamos futásnál nincs modul-szintű, mutálódó állapot —
  egy megosztott kiosztás két irat elemzését keverné össze, és a hiba
  **nem-determinisztikus** lenne.
- **Atomikus mentés:** tmp + `fsync` + `replace`. ⚠ **Zár még nincs** — nyitott
  tétel.
- **A támogatott formátumok egy helyen** definiáltak (`extension_routing`).
- **A kétértelműség hiba, nem választás** — fejléc-illesztésnél, profil-
  felismerésnél és címke-kinyerésnél egyaránt. A „válassz valamit" viselkedés
  **működne**, és épp ezért veszélyes.
- **A mérőeszköz is állítás, és neki is kell bizonyíték.** Minden kapu mellé
  negatív **és** pozitív kontroll jár; a kapu-készletet
  `tools/mutation_check.py` méri, és a **nem fedett** eseteket megnevezi.

---

## Amit ezekből drágán tanultunk — konkrétan

Ezek nem elvont figyelmeztetések: mindegyik **megtörtént**, és a kapu attól van,
hogy másodszor ne történhessen meg.

| Mi történt | Melyik elv védi ma |
|---|---|
| A `save()` **előbb csonkolta** a fájlt, mint hogy elbukott volna az ellenőrzésen — egy meglévő, helyes config nullára íródott volna. | fail-closed mentés, ellenőrzés a fájl megnyitása **előtt** |
| A titok-kapu `asdict()`-en iterált, tehát a futásidőben hozzáadott mezőt **nem is látta**. | `vars()`-alapú kapu — a kapu ne legyen vak arra, ami ellen véd |
| A határ-kapu `glob`-bal listázott, tehát egy **alcsomag csendben kimaradt** volna. | `rglob` + relatív út a kulcsban |
| A szabványkönyvtár elválasztó-felismerője **nem bukik el, hanem tippel** — a szóközt választotta, és a fejléc szavakra esett szét. | zárt jelölt-lista + determinisztikus, fejléc-alapú szabály |
| A tudományos-alak detektor **vak volt a 2⁵³…1e16 sávra**: ott a számjegyek már elvesztek, de a vizsgálat nem fogott. | külön ág az ábrázolás kemény határára |
| A sor-üresség az **értelmezett** megbízhatóságból dolgozott, ezért egy gyorsítótár nélküli képlet **csendben kiütötte az egész sort**. | az üresség a **bemenet** tulajdonsága, nem az értelmezés eredménye |
| Egy rövidebb címke (`Adó`) **elszívta** egy hosszabb mező (`Adóalap`) sorát — és a hibát **elmaszkolta a származtatás**, a *helyes* értékkel. | szóhatár + **leghosszabb címke nyeri a sort**; és a származtatás **soha nem `CONFIRMED`** |
| A semlegességi kapu a **tervdokumentumban** talált cél-rendszer-nevet — ott, ahol nem is a kódot néztük. | a kapu a **teljes repót** vizsgálja, nem csak a forrást |

> A közös nevező mindegyikben: **a rendszer javasol és jelöl, az ember dönt, és a
> döntésből tudás lesz.** Ez a termék — nem a felismerés.
