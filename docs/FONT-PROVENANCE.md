# A szállított betűtípus — eredet, licenc, és amit megmértünk

> **Döntés:** Gábor, 2026-08-03. *Szállítjuk a LiberationSans-t OFL-1.1 alatt,
> és emellett legyen konfigurálható felülírás; hiányzó vagy nem fedő betűtípus
> esetén **fail-closed**.*

## Miért van a csomagban egyáltalán betűtípus

A kereshető PDF **láthatatlan szövegréteget** ír a lapra, és ehhez **beágyazott**
betűtípus kell. A PDF beépített („base 14") betűtípusai — köztük a Helvetica —
a magyar hosszú ékezeteket **nem hordozzák**, és ezt **némán** teszik.

Mérve (DC-01 terv, 2026-07-30) — ugyanaz a hibás PDF, két olvasó,
**három különböző hibaalak**. Bemenet: `'Tuzolto őrs arviztuűro'`, hossz 22.

| Betűtípus | `pypdf.extract_text` | `pypdfium2.get_text_bounded` |
|---|---|---|
| **LiberationSans (OFL)** | `'Tuzolto őrs arviztuűro'` — hossz **22** ✅ | hossz **22** ✅ |
| Helvetica (beépített) | `'Tuzolto ■rs arviztu■ro'` — hossz **22** | `'Tuzolto '` — hossz **8** |

⚠ **A Helvetica-sor bal oldala a veszélyes:** a **hossz stimmel**, csak a
karakter rossz. Egy hossz-alapú vagy „nincs tiltott karakter" típusú ellenőrzés
ezen **üresen zöld**. És mindez a **láthatatlan** rétegben történik, tehát a
kimenetre nézve soha nem derül ki — csak akkor, amikor egy ügyfél nem találja
meg a saját dokumentumát a keresőben.

## A szállított példány

| | |
|---|---|
| Fájl | `src/doccapture/resources/LiberationSans-Regular.ttf` |
| Méret | 410 712 bájt |
| `sha256` | `76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8` |
| Projekt | `liberationfonts/liberation-fonts` |
| Kiadás | **2.1.5**, 2021-09-30 |
| Forrás-csomag | `liberation-fonts-ttf-2.1.5.tar.gz` |
| A csomag `sha256`-ja | `7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0` |
| Licenc | **OFL-1.1** (`SIL Open Font License 1.1`) |
| Fenntartott név | `Liberation` (valamint `Arimo`, `Tinos`, `Cousine`) |

A példány a **kiadás hivatalos, épített csomagjából** származik (a 2.1.5 kiadás
szövegében közzétett letöltés), nem egy gépen talált másolatból.

> **Mellékes, de megnyugtató:** a fejlesztői gép rendszer-font mappájában
> (`C:/Windows/Fonts/`) lévő azonos nevű példány `sha256`-ja **egyezik** a
> fentivel — vagyis a terv korábbi mérései is ugyanezeken a bájtokon készültek.
> Ez **utólagos egyezés**, nem a proveniencia forrása: egy rendszer-mappában
> talált fájlról nem bizonyítható, melyik kiadás.

## Amit MEGMÉRTÜNK a betűtípuson

A mérést a `tools/binary_guard.py` végzi, **függőség nélkül** (saját, `struct`
alapú `cmap` olvasó) — épp azért, hogy a mérés ne függjön attól, van-e bármilyen
betűtípus-könyvtár telepítve.

| Mérés | Eredmény |
|---|---|
| A megkövetelt karakterkészlet fedése | **90 karakter mérve, 0 hiányzik** |
| A magyar hosszú ékezetek (`ő ű Ő Ű`) | mind valódi glyph-ID-vel |
| **Pozitív kontroll** — amit *nem* szabad fednie (CJK, katakana) | helyesen **hiányzik** |
| `OS/2` `fsType` | **0** = Installable Embedding, korlátozás nélkül |

⚠ A pozitív kontroll nélkül a „minden karakter megvan" válasz jelenthetné azt is,
hogy a `cmap`-olvasónk mindig nem-nullát ad. Egy mérőeszköz, ami mindig igent
mond, megkülönböztethetetlen attól, amelyik el sem indul.

## Licenc-kötelezettségek — amit vállalunk

Az OFL-1.1 négy dolgot kér, és mind a négy teljesül:

1. **A licencet tovább kell adni a fonttal.** → `LICENSE-LiberationSans.txt`
   ugyanabban a könyvtárban, és a csomag-metaadatban is
   (`[tool.setuptools.package-data]`) — *egy fájl a repóban nem jut el a
   fogyasztóhoz.*
2. **A copyright-jelzés marad.** → a licenc-fájl elején, változatlanul.
3. **A betűtípust önmagában nem áruljuk.** → a motor a termék, a font
   beágyazott erőforrás.
4. **Módosított származékot át kell nevezni** (Reserved Font Name: `Liberation`).
   → **ma nem módosítunk betűtípust.** Ha valaha módosítunk, az **külön kaput**
   igényel; a `binary_artifacts.json` `_not_covered` szakasza ezt nevesíti.

### Amit ez a vevőnek jelent — ez eladási érv, nem teher

Az OFL **kifejezetten engedi** a dokumentumba ágyazást, és a beágyazástól **a
keletkező PDF nem lesz OFL-es**. Vagyis az ügyfél kimenete **licenc-mentes
marad** — a motor licenc-fegyelme nem terjed át a vevő irataira.

## A gépi kapu — és amit szándékosan nem mér

A `tools/binary_guard.py` a CI-ben fut, és **négy külön kérdést** mér:
engedélyezett-e (deklarálva van-e), az-e aminek mondjuk (`sha256`), megvan-e a
licenc, és **használható-e** a betűtípus.

⚠ **Miért kellett külön kapu:** a licenc-kapu (`tools/license_guard.py`, G5)
**csak pip-csomagokat lát**. Egy szállított *nem-pip* artefaktum licence enélkül
**mérés nélkül** maradna — a `LICENSE` fájl ott lehet a repóban, a G5-öt őrző
gépi kapu **akkor sem tud róla**.

**Amit nem mér:** a licenc jogi értelmezését, a betűtípus vizuális minőségét
(hinting, kerning), és a módosított származék átnevezési kötelezettségét (ma
nincs mit mérni).

## Konfigurálható felülírás

A döntés második fele: az ügyfél **saját, jogtiszta betűtípust** tehet be. Ez a
**DC-01b** szelet része (a betöltő adapter és a fail-closed
`FontUnusableError`); ez a dokumentum a **szállított alapértelmezést** rögzíti.

## Ha frissíteni kell a betűtípust

1. Töltsd le a **kiadás hivatalos csomagját**, és ellenőrizd a csomag `sha256`-ját.
2. Cseréld a fájlt, majd `python tools/binary_guard.py` → a hash-eltérést
   **jelezni fogja** (ez a szándék: néma csere ne legyen).
3. Írd át a `tools/binary_artifacts.json` `sha256`, `origin_release`,
   `origin_released_at`, `origin_url`, `origin_archive_sha256` mezőit **és ezt a
   dokumentumot**.
4. Futtasd újra a kaput: a glyph-fedést és az `fsType`-ot **újra megméri** — egy
   új kiadás elveszíthet lefedettséget, és ezt nem szabad feltételezésre bízni.
