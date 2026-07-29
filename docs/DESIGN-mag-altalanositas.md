# A mag általánosítása — design intent

> Mit emeltünk át egy korábbi, éles használatban kiforrott megoldásból, **mit
> változtattunk meg szándékosan, és mit hagytunk ki tudatosan.**
> A végeredmény önmagában nem magyarázza el, miért ilyen — ezt rögzíti ez a lap.

## Amit átvettünk, mert bevált

- **Hexagonális határ:** a magban nincs infrastruktúra-import.
- **Minden konfigurálható érték egy helyen**, alapértékkel.
- **A támogatott formátumok egyetlen helyen** vannak definiálva.
- **Újrapróbálás exponenciális várakozással**, és atomikus mentés.
- **Portok** a felismeréshez, a dokumentum-építéshez, a tároláshoz és a
  kereséshez.

## Amit szándékosan MÁSKÉNT csinálunk

### 1. A mag nem ismeri az adaptereket

A forrás configjában gyártó-nevű kulcsok álltak (felismerő-motorok, vektortár és
modell-szolgáltató paraméterei, tucatnyi mező). Ettől a domain **tudott** az
infrastruktúráról: a config megnevezte, mi van mögötte.

Itt minden ilyen az `adapter_options` alá megy — adapter-név → szabad kulcs-érték
—, amit a mag **nem értelmez**, csak továbbad. Így az adapter cserélhető anélkül,
hogy a mag változna. *Ez az egész hexagonális felállás értelme; enélkül a
könyvtárszerkezet hexagonális, a függőségek nem.*

### 2. Titok nem kerülhet a configba

A forrás configjában volt kulcs-mező, **és** a config kiírta magát JSON-ba —
vagyis a titok lemezre került. Itt csak a környezeti változó **neve** tárolható
(`credential_env`), az **értéke** soha; ezt teszt is őrzi, és a mentés
**fail-closed** (inkább bukik, mint hogy titkot írjon ki).

Fontos megkülönböztetés, amit a kapu is tud: **a változó-hivatkozás nem titok.**
Egy kapu, ami a hivatkozásokat is buktatja, egy héten belül ki lenne kapcsolva —
és akkor rosszabbul állnánk, mint kapu nélkül.

### 3. Nincs beégetett ország, nyelv vagy pénznem

A forrásban a nyelvlista és a pénznem alapértéke egy konkrét országra mutatott.
Itt az üres alapérték azt jelenti: *„az adapter döntse el"* — nem azt, hogy
bármelyik konkrét ország.

### 4. A biztonságos viselkedés az ALAPÉRTELMEZÉS

`read_only_source=True`, `run_active_content=False`,
`preserve_original_units=True`. Nem bekapcsolható extra, hanem alapállapot — aki
eltér tőle, az döntsön róla kimondottan.

Az aktív tartalom tiltása **nem csak biztonsági** kérdés: egy futtatott képlet ma
és holnap mást adhat, tehát a determinizmus is elveszne.

### 5. A negyedik út portja új

A forrásban **nem volt** táblázatos út — pedig egy cég integrálásakor az adatok
többsége már digitális. Ha ezt is a felismerő úton oldanánk meg, a legolcsóbb
esetet fizetnénk meg a legdrágábban, és modellt engednénk oda, ahol a
determinisztikus feldolgozás a helyes válasz. Ezért a `TabularReader` **port**
már most létezik (adapter nélkül).

### 6. A nyers pontszám nem azonos a megbízhatósággal

A felismerő saját pontszáma (`TextFragment.raw_confidence`, 0.0-1.0) és a domain
`Confidence` szintjei **szándékosan külön** élnek. Egy 0.91-es pontszám nem
jelenti, hogy az érték megerősített — azt üzleti ellenőrzés (pl. redundancia)
döntheti el. A kettő összemosása lenne a legkönnyebb hiba.

### 7. A hiányzó mező nem kivétel

Kivételt csak akkor dobunk, ha **magát a forrást** nem tudtuk feldolgozni. Egy
hiányzó mező **adat** (`MISSING`), nem hiba — különben a hívó kivétel-kezeléssel
próbálná lekezelni azt, ami valójában eredmény.

## Amit tudatosan KIHAGYTUNK

**A számla-kinyerő portot és adatszerkezeteit.** Két okból:

1. **Ez a G1 kapu tárgya** — két igazság van kialakulóban ugyanarról. Amíg nincs
   döntés, a magba bemásolni azt jelentené, hogy a kérdést kódba írt tényként
   előredöntjük.
2. **Nem is ide tartozik.** A sorok értelmezése — kód-párosítás, mennyiség-átváltás
   — nem az *„mi van a papíron"* kérdés, hanem a *„mi kerüljön a rendszerbe"*.
   Az az iparági réteg dolga, és ott determinisztikus szabály + ember, nem modell.

A forrás adatszerkezete beégetett pénznemmel és szöveges állapot-mezővel
dolgozott: **mintaként tanulság, receptként hiba lett volna.**

Ezt teszt őrzi (`test_ports.GateTests`): ha egyszer elbukik, az nem hiba, hanem
**jelzés, hogy valaki a kapu előtt lépett**.

## Gépi kapuk, amiket ez a kör hozott

| Kapu | Mit állít | Hogyan bizonyítottuk |
|---|---|---|
| `test_core_boundary` | a magban nincs infrastruktúra-import | mutációval: külső csomag **és** saját infrastruktúra-réteg importja is elbukott |
| `test_config` | titok nem kerülhet configba, a mentés fail-closed | a teszt **valódi hibát talált**: a mentés a fájlt előbb csonkolta, mint hogy elbukott volna |
| `test_ports` | a négy út külön port, és a G1 tárgya nincs a magban | üres-halmaz elleni védelem (a teszt elbukik, ha nem talál portot) |

A forrás-projekt kimondta a hexagonális szabályt — de **csak dokumentációban**.
Egy szabály, amit nem mér senki, előbb-utóbb megsérül, és pont az ilyen sérülés
marad csendben: a kód működik, csak éppen a domain kezd tudni a külvilágról.
