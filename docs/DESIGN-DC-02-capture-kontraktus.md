# DC-02 — a Capture-kontraktus (tervezési szándék)

> **Cél:** a motor kimenete **publikált, hash-pinnelt szerződés** mögé kerül, hogy
> a platform-modul fogyaszthassa **anélkül, hogy a motor belsejéről tudna** — és
> hogy a motor **cserélhető** legyen.
>
> **Leállási feltétel (QUALITY §1):** a szelet akkor kész, ha (1) a kontraktus
> publikált fájl, nem melléktermék; (2) a hash **a teljes wire-tartalmat** fedi,
> és ezt **mérjük**, nem feltételezzük; (3) a `.NET` oldal a szerződésből
> dolgozik, és a DTO-eltérés **build-hibát** ad; (4) mindkét irány zárt: nem
> dokumentált mező és nem előállított mező is elbukik.

---

## 1. A LEGFONTOSABB DÖNTÉS: ez ADAT-szerződés, nem HTTP-API

Csábító lenne a scheduling mintáját szó szerint másolni (OpenAPI 3.1 +
végpont-tábla + generált kliens). **De ott egy futó szolgáltatás API-ja volt a
szerződés; itt nem az.**

Miért nem:

- **A G4-döntés (helyi alap, külső opcionális) miatt a motor futhat
  in-process is.** Egy HTTP-API feltételezné a telepítési alakot — pont azt,
  amit a G4 szándékosan **konfigurációnak** hagyott.
- A motor **könyvtár és eszköz**, nem szerver. Aki csak a Python-motort veszi
  meg, annak nem kell HTTP-réteg.

**Ezért a szerződés a `CaptureRecord` WIRE-ALAKJA** — JSON Schema 2020-12
(OpenAPI 3.1-kompatibilis). Ez működik akkor is, ha a motort **in-process**
hívják, ha **soron** megy át, és akkor is, ha később **HTTP** kerül elé: a
szállítás cserélhető, az **alak** nem.

> Ez a scheduling-minta **lényegének** átvétele, nem a formájának: ott is az volt
> a lényeg, hogy a szerződés **forrás-igazság**, kétirányú kapuval és generált
> fogyasztóval — nem az, hogy YAML-ban végpontok álltak.

## 2. A hash a WIRE-TARTALMAT fedi — és ezt MÉRJÜK

Az epic figyelmeztetése szó szerint: *„Ha egy mező kimegy a wire-ra, de a
hash-en kívül marad, a hash megszűnik identitás lenni. Származtatott mezőt akkor
nem kell hashelni, ha **minden bemenete** hashelve van — és ezt a premisszát
**ellenőrizni kell**, nem feltételezni."*

Három kapu ebből:

1. **Minden előállított mező szerepel a sémában.** A szerializáló kimenetének
   minden kulcsa a hashelt sémában van. *(Negatív kontroll: egy séma nélküli
   mező felvétele elbukik.)*
2. **Minden sémában deklarált mező elő is áll.** Enélkül egy mező „csendben
   megszűnhetne mérve lenni" — a scheduling ugyanezt a rést zárta be.
3. **A származtatott mező premisszája mérve.** A wire-on egyetlen származtatott
   mező van: `needs_human`. A premissza az, hogy **minden bemenete a wire-on
   van** (az összes érték megbízhatósága). A kapu ezt nem elhiszi, hanem
   **újraszámolja a wire-ból**, és összeveti.

**A pin egy külön fájl** (`contracts/capture-record.pin.json`): a séma
SHA-256-ja + a szerződés-verzió. A hash **a séma bájtjait** fedi — ha akár egy
karakter változik, a pin nem stimmel, és a kapu elbukik. Ez a *„mit hasheltünk"*
kimondása: nem „a kontraktus hashe", hanem **a `capture-record.schema.json`
bájtjainak** SHA-256-ja.

## 3. Mi megy a wire-ra, és mi NEM

| Wire-mező | Miért |
|---|---|
| `contract_version` | a fogyasztó a **fő verziót** ellenőrzi; enélkül a törő változás csendben téves adatot ad |
| `input_kind` | a négy út melyikén jött — a fogyasztónak más a bizalma egy táblázathoz és egy kézíráshoz |
| `evidence` | relatív út + `sha256:`-előtagos tartalom-hash + hely (M13) |
| `fields` / `rows` | érték + **megbízhatóság** + indok + cella-szintű bizonyíték |
| `diagnostics` | amit észrevettünk, de **nem javítottunk** — ez a fogyasztónak szól |
| `needs_human` | **származtatott**, kényelmi mező; a premisszája mérve (ld. fent) |

**Ami NEM megy ki:** abszolút útvonal · titok · a motor belső típusnevei · a
használt könyvtárak neve. A szerződésnek **nem szabad elárulnia**, mi van
mögötte — különben a motor cserélhetetlen lesz.

### Az érték-típus a wire-on: `value_type`

A wire **öndokumentáló**: minden értéknél ott áll, hogy a JSON-ban milyen alakban
utazik (`text` · `number` · `integer` · `boolean` · `date`). Ez azért kell, mert a
dátum ISO-8601 **sztringként** utazik — platform-oldali könyvtár-választás nem
kerül a wire-ra —, és a fogyasztónak tudnia kell, hogy az a sztring dátum.

⚠ **Amit ez NEM tud, és kimondjuk:** `MISSING` értéknél **nincs** érték, tehát a
`value_type` sem levezethető — ott `null` megy ki. A fogyasztó a **szándékolt**
típust a saját sémájából/profiljából tudja, nem a wire-ból. Ez ismert rés, nem
elnézés.

## 4. A `.NET` oldal: a szerződés a build-be kötve

A modul-repó a séma **vendorolt másolatát** és a **pint** tartalmazza, és három
kapu köti a kódhoz:

1. **Pin-egyezés:** a vendorolt séma SHA-256-ja egyezik a pinben állóval. Ha a
   motor változtat és a modul nem frissít, ez azonnal piros.
2. **DTO ⇄ séma, mindkét irány:** minden séma-property kötve van DTO-taghoz, és
   minden DTO-tag szerepel a sémában. *(Nem elég az egyik: egy dokumentált, de
   nem kötött property csendben megszűnne mérve lenni.)*
3. **Aranypéldány-beolvasás:** a motor által **valóban előállított** JSON-t
   deszerializáljuk a DTO-kba, és visszaellenőrizzük. Egy séma-egyezés még nem
   bizonyítja, hogy a **tényleges** kimenet beolvasható.

### Előre-kompatibilitás: a fogyasztó ismeretlen mezőn NEM bukhat el

Additív bővítés esetén a modul régebbi verziója **ismeretlen mezőket** fog látni.
A szabály:

- **ismeretlen mező → átengedjük** (a bővítés ne törje a fogyasztót);
- **ismeretlen FŐ verzió → elbukunk** (a törő változás ne adjon csendben téves
  adatot).

Ez a kettő együtt adja, hogy a verzió-emelés **kimondott** lehet, és mégis
biztonságos. Mindkettőt teszt méri.

## 5. Amit szándékosan NEM építünk ebben a szeletben

- **Nincs HTTP-végpont.** Ld. §1 — az a telepítési alak kérdése, és a G4 azt
  konfigurációnak hagyta.
- **Nincs DMS-tárolás és nincs jogosultság-kezelés.** Az a DC-01, és a modul
  README-je is arra teszi. Ez a szelet a **határt** építi, nem a tárolást.
- **Nincs NuGet-publikálás.** A csomagolás külön, kimondott lépés lesz.
- **Nincs generált Python-kliens.** A motor a **kibocsátó**, nem fogyasztó.

## 6. Amit előre kimondunk: mit NEM fog tudni

1. **A sorok (`rows`) séma-szinten homogének.** Egy iraton, ahol két különböző
   tétel-tábla van, a wire nem különíti el őket — ma egy `rows` van.
2. **A `value_type` `MISSING` esetén `null`** (ld. §3).
3. **A pin a séma bájtjait fedi, nem a szemantikát.** Egy pusztán formázási
   változás (behúzás) is új pint ad. Ez **szándékos** — a hamis nyugalom
   rosszabb, mint egy fölösleges pin-frissítés.
4. **A `.NET` oldalon nincs végpont, tehát route-drift kapu sincs** — az a
   scheduling-mintából itt **nem** értelmezhető, és ezt kimondjuk, nem
   „teljesítettnek" nevezzük.
