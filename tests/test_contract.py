"""A Capture-kontraktus kapui — a hash a WIRE-TARTALMAT fedi.

AZ EPIC FIGYELMEZTETÉSE, SZÓ SZERINT
------------------------------------
*„A hash fedje a wire-tartalmat. Ha egy mező kimegy a wire-ra, de a hash-en kívül
marad, a hash megszűnik identitás lenni. Származtatott mezőt akkor nem kell
hashelni, ha **minden bemenete** hashelve van — és ezt a premisszát
**ellenőrizni kell**, nem feltételezni."*

Ez a fájl ebből három kaput csinál:

1. **Minden előállított mező szerepel a sémában** (`WireCoveredBySchemaTests`);
2. **minden sémában deklarált mező elő is áll** (`SchemaCoveredByWireTests`) —
   enélkül egy mező „csendben megszűnhetne mérve lenni";
3. **a származtatott mező premisszája mérve** (`DerivedFieldPremiseTests`): a
   `needs_human`-t **újraszámoljuk a wire-ból**, és összevetjük.

Mindháromhoz **negatív kontroll** jár: enélkül nem tudnánk, hogy a kapu azért
zöld, mert a szerződés zárt — vagy azért, mert a mérés sosem talál semmit.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import unittest
from pathlib import Path

from doccapture.core.models import (
    CaptureRecord,
    Confidence,
    Extracted,
    InputKind,
    SourceEvidence,
)
from doccapture.infrastructure.wire import (
    CONTRACT_VERSION,
    recompute_needs_human,
    record_to_wire,
)

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / "contracts" / "capture-record.schema.json"
PIN_PATH = REPO / "contracts" / "capture-record.pin.json"

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
EVIDENCE = SourceEvidence("alkonyvtar/irat.txt", "sha256:abc123", "L7")


def _full_record() -> CaptureRecord:
    """Olyan rekord, amiben MINDEN wire-mező szerepel, és minden érték-típus.

    Ez a mérés érvényességének feltétele: ha a próba-rekord nem tölt ki minden
    mezőt, a „minden előállított mező benne van a sémában" állítás **csak arra a
    részhalmazra** igaz, amit épp kitöltöttünk — és a mérés nem mondja meg, mi
    maradt ki.
    """
    return CaptureRecord(
        input_kind=InputKind.TABULAR,
        evidence=SourceEvidence("alkonyvtar/irat.txt", "sha256:abc123"),
        fields={
            "szoveg": Extracted("Megnevezés", Confidence.CONFIRMED, EVIDENCE),
            "szam": Extracted(12.5, Confidence.CONFIRMED, EVIDENCE),
            "egesz": Extracted(7, Confidence.CONFIRMED, EVIDENCE),
            "logikai": Extracted(True, Confidence.CONFIRMED, EVIDENCE),
            "datum": Extracted(dt.date(2026, 7, 30), Confidence.CONFIRMED, EVIDENCE),
            "idopont": Extracted(
                dt.datetime(2026, 7, 30, 12, 0), Confidence.CONFIRMED, EVIDENCE
            ),
            "jelolt": Extracted(3.0, Confidence.NEEDS_REVIEW, EVIDENCE, "származtatva"),
            "hianyzo": Extracted(None, Confidence.MISSING, EVIDENCE, "üres cella"),
            "bizonyitek_nelkul": Extracted("x", Confidence.CONFIRMED, None),
        },
        rows=[{"kod": Extracted("A-1", Confidence.CONFIRMED, EVIDENCE)}],
        diagnostics=["1 sor üresként kihagyva"],
    )


def _leaf_paths(value, prefix: str = "") -> set[str]:
    """A wire minden LEVÉL-mezőjének útvonala (`fields.*.confidence` alakban).

    A szótár-kulcsok (mező-nevek) helyére `*` kerül: azok **adat**, nem
    szerződés — a szerződés azt írja le, hogy egy értéknek milyen tagjai vannak,
    nem azt, hogy a mezőt hogyan hívják.
    """
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            paths |= _leaf_paths(item, f"{prefix}{key}.")
        if not value:
            paths.add(prefix.rstrip("."))
    elif isinstance(value, list):
        for item in value:
            paths |= _leaf_paths(item, prefix)
        if not value:
            paths.add(prefix.rstrip("."))
    else:
        paths.add(prefix.rstrip("."))
    return paths


def _wire_shape(wire: dict) -> set[str]:
    """A wire szerkezete: felső mezők + az `extracted`/`evidence` tagjai."""
    shape = set(wire.keys())
    shape |= {f"evidence.{k}" for k in wire["evidence"]}
    for item in list(wire["fields"].values()) + [
        v for row in wire["rows"] for v in row.values()
    ]:
        shape |= {f"extracted.{k}" for k in item}
        if item.get("evidence"):
            shape |= {f"evidence.{k}" for k in item["evidence"]}
    return shape


def _schema_shape() -> set[str]:
    """A séma szerkezete ugyanabban az alakban — hogy összevethető legyen."""
    shape = set(SCHEMA["properties"])
    shape |= {f"evidence.{k}" for k in SCHEMA["$defs"]["evidence"]["properties"]}
    shape |= {f"extracted.{k}" for k in SCHEMA["$defs"]["extracted"]["properties"]}
    return shape


class WireCoveredBySchemaTests(unittest.TestCase):
    """1. kapu: minden ELŐÁLLÍTOTT mező szerepel a hashelt sémában."""

    def test_minden_wire_mezo_a_semaban_van(self) -> None:
        hianyzo = _wire_shape(record_to_wire(_full_record())) - _schema_shape()
        self.assertEqual(
            hianyzo,
            set(),
            f"a wire-ra kimegy, de a HASHELT semaban nincs: {sorted(hianyzo)}. "
            f"Ilyenkor a hash megszunik identitas lenni erre a mezore.",
        )

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        """Egy séma nélküli mező felvétele elbukik."""
        wire = record_to_wire(_full_record())
        wire["uj_nem_dokumentalt_mezo"] = "x"
        self.assertIn("uj_nem_dokumentalt_mezo", _wire_shape(wire) - _schema_shape())

    def test_a_probarekord_MINDEN_ertek_tipust_tartalmaz(self) -> None:
        """A mérés érvényességének feltétele: ha a próba-rekord nem tölt ki minden
        típust, az 1. kapu csak arra a részhalmazra állít valamit."""
        wire = record_to_wire(_full_record())
        tipusok = {item["value_type"] for item in wire["fields"].values()}
        self.assertEqual(
            tipusok,
            {"text", "number", "integer", "boolean", "date", None},
            "a proba-rekord nem fedi minden ertek-tipust — a meres reszleges",
        )


class SchemaCoveredByWireTests(unittest.TestCase):
    """2. kapu: minden SÉMÁBAN DEKLARÁLT mező elő is áll.

    Enélkül egy mező **csendben megszűnhetne mérve lenni**: benne marad a
    sémában, a fogyasztó számol vele, de a motor már nem adja.
    """

    def test_minden_sema_mezo_eloall(self) -> None:
        nem_eloallo = _schema_shape() - _wire_shape(record_to_wire(_full_record()))
        self.assertEqual(
            nem_eloallo,
            set(),
            f"a semaban all, de a motor NEM adja: {sorted(nem_eloallo)}. "
            f"A fogyaszto szamolna vele, es soha nem kapna meg.",
        )

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        wire = record_to_wire(_full_record())
        wire.pop("diagnostics")
        self.assertIn("diagnostics", _schema_shape() - _wire_shape(wire))


class DerivedFieldPremiseTests(unittest.TestCase):
    """3. kapu: a származtatott mező PREMISSZÁJA mérve.

    A `needs_human` származtatott. A premissza: **minden bemenete a wire-on van**.
    Ezt nem elhisszük — **újraszámoljuk a wire-ból**, és összevetjük.
    """

    def test_a_needs_human_ujraszamolhato_a_WIRE_bol(self) -> None:
        for record in (_full_record(), _all_confirmed_record()):
            with self.subTest(needs_human=record.needs_human):
                wire = record_to_wire(record)
                self.assertEqual(
                    recompute_needs_human(wire),
                    wire["needs_human"],
                    "a szarmaztatott mezo NEM ujraszamolhato a wire-bol — tehat a "
                    "hash arra a mezore megszunt identitas lenni",
                )

    def test_egyetlen_bizonytalan_ertek_is_igazza_teszi(self) -> None:
        """Nem átlagolunk: egy 5000 soros betöltésben egy hibás sor átlagolva
        eltűnik, pedig épp az az egy sor a lényeg."""
        record = _all_confirmed_record()
        self.assertFalse(record_to_wire(record)["needs_human"])

        record.rows.append(
            {"kod": Extracted(None, Confidence.MISSING, EVIDENCE, "üres")}
        )
        wire = record_to_wire(record)
        self.assertTrue(wire["needs_human"])
        self.assertTrue(recompute_needs_human(wire))

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        """Ha a megbízhatóság NEM lenne a wire-on, az újraszámolás nem tudná
        előállítani az igaz értéket — és a kapu ezt észreveszi."""
        wire = record_to_wire(_full_record())
        self.assertTrue(wire["needs_human"])
        for item in wire["fields"].values():
            item["confidence"] = Confidence.CONFIRMED.value
        self.assertNotEqual(recompute_needs_human(wire), wire["needs_human"])


def _all_confirmed_record() -> CaptureRecord:
    return CaptureRecord(
        input_kind=InputKind.TABULAR,
        evidence=SourceEvidence("irat.txt", "sha256:abc"),
        fields={"a": Extracted("x", Confidence.CONFIRMED, EVIDENCE)},
        rows=[{"kod": Extracted("A-1", Confidence.CONFIRMED, EVIDENCE)}],
    )


class WireDisciplineTests(unittest.TestCase):
    """Amit a wire SOHA nem árulhat el."""

    def test_a_wire_nem_tartalmaz_ABSZOLUT_utat(self) -> None:
        """Egy abszolút út felfedi a gépi könyvtárszerkezetet, és a bizonyíték
        átvihetetlen lesz egy másik telepítésre."""
        szoveg = json.dumps(record_to_wire(_full_record()), ensure_ascii=False)
        for jel in ("C:/", "C:\\", "/home/", "/Users/", "/opt/"):
            with self.subTest(jel=jel):
                self.assertNotIn(jel, szoveg)

    def test_a_wire_nem_tartalmaz_belso_tipusnevet(self) -> None:
        """Ha a szerződés elárulja, mi van mögötte, a motor cserélhetetlen lesz."""
        szoveg = json.dumps(record_to_wire(_full_record()), ensure_ascii=False)
        for nev in ("Extracted", "CaptureRecord", "SourceEvidence", "openpyxl", "doccapture"):
            with self.subTest(nev=nev):
                self.assertNotIn(nev, szoveg)

    def test_a_datum_ISO_sztringkent_utazik(self) -> None:
        """Platform-oldali könyvtár-választás nem kerül a wire-ra."""
        wire = record_to_wire(_full_record())
        self.assertEqual(wire["fields"]["datum"]["value"], "2026-07-30")
        self.assertEqual(wire["fields"]["datum"]["value_type"], "date")

    def test_az_IDOPONT_datumra_csonkul_es_ezt_a_tipus_kimondja(self) -> None:
        wire = record_to_wire(_full_record())
        self.assertEqual(wire["fields"]["idopont"]["value"], "2026-07-30")
        self.assertEqual(wire["fields"]["idopont"]["value_type"], "date")

    def test_a_LOGIKAI_ertek_nem_szamkent_megy_ki(self) -> None:
        """A `bool` a Pythonban `int`: ha a szám-ágat vizsgálnánk előbb, a `True`
        `1`-ként utazna, és a fogyasztó számot látna logikai mező helyén."""
        wire = record_to_wire(_full_record())
        self.assertIs(wire["fields"]["logikai"]["value"], True)
        self.assertEqual(wire["fields"]["logikai"]["value_type"], "boolean")

    def test_a_HIANY_bizonyitekot_is_hordoz(self) -> None:
        """A hiány is adat, tehát annak IS van bizonyítéka."""
        hianyzo = record_to_wire(_full_record())["fields"]["hianyzo"]
        self.assertIsNone(hianyzo["value"])
        self.assertIsNone(hianyzo["value_type"])
        self.assertEqual(hianyzo["confidence"], "missing")
        self.assertIsNotNone(hianyzo["evidence"])
        self.assertEqual(hianyzo["note"], "üres cella")

    def test_a_wire_JSON_kent_kiirhato_es_visszaolvashato(self) -> None:
        wire = record_to_wire(_full_record())
        self.assertEqual(json.loads(json.dumps(wire, ensure_ascii=False)), wire)


class PinTests(unittest.TestCase):
    """A pin a séma bájtjait fedi, és **kimondja**, mit hasheltünk."""

    def test_a_pin_EGYEZIK(self) -> None:
        proc = subprocess.run(
            [sys.executable, "tools/contract_pin.py"], cwd=REPO, capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_a_pin_MEGNEVEZI_a_hashelt_bemenetet(self) -> None:
        """Egy hash önmagában nem azonosít semmit, ha nem tudjuk, mi a bemenete —
        ebből lett 2026-07-29-en egy hamis „harmadik token"."""
        pin = json.loads(PIN_PATH.read_text(encoding="utf-8"))
        self.assertIn("hashed_input", pin)
        self.assertIn("capture-record.schema.json", pin["hashed_input"])
        self.assertTrue(pin["digest"].startswith("sha256:"))

    def test_a_HAROM_verzio_egy_igazsag(self) -> None:
        """A séma `$id`-je, a pin és a szerializáló ugyanazt a verziót mondja.
        Három helyen álló verzió három igazság lenne, és a fogyasztó **épp a
        verzió alapján** ismeri fel a törő változást."""
        pin = json.loads(PIN_PATH.read_text(encoding="utf-8"))
        sema_verzio = SCHEMA["$id"].rstrip("/").rsplit("/", 1)[-1]
        self.assertEqual(pin["contract_version"], sema_verzio)
        self.assertEqual(CONTRACT_VERSION, sema_verzio)

    def test_a_wire_a_SAJAT_verziojat_adja(self) -> None:
        self.assertEqual(record_to_wire(_full_record())["contract_version"], CONTRACT_VERSION)


class SchemaValidationTests(unittest.TestCase):
    """A séma maga is érvényes és zárt legyen."""

    def test_a_sema_ZART_nem_engedi_at_az_ismeretlen_mezot(self) -> None:
        """`additionalProperties: false` — enélkül a szerződés nem szerződés:
        bármit ki lehetne küldeni, és a kapu 1. iránya értelmét vesztené."""
        self.assertFalse(SCHEMA["additionalProperties"])
        self.assertFalse(SCHEMA["$defs"]["evidence"]["additionalProperties"])
        self.assertFalse(SCHEMA["$defs"]["extracted"]["additionalProperties"])

    def test_a_KOTELEZO_mezok_mind_eloallnak(self) -> None:
        wire = record_to_wire(_full_record())
        for kulcs in SCHEMA["required"]:
            with self.subTest(kulcs=kulcs):
                self.assertIn(kulcs, wire)

    def test_a_bemeneti_utak_ENUMJA_egyezik_a_motorral(self) -> None:
        """Ha a séma enumja elcsúszik, egy új bemeneti út csendben szerződés-sértő
        értéket küldene ki."""
        self.assertEqual(
            sorted(SCHEMA["properties"]["input_kind"]["enum"]),
            sorted(kind.value for kind in InputKind),
        )

    def test_a_megbizhatosag_ENUMJA_egyezik_a_motorral(self) -> None:
        self.assertEqual(
            sorted(SCHEMA["$defs"]["confidence"]["enum"]),
            sorted(c.value for c in Confidence),
        )


class LineEndingTests(unittest.TestCase):
    """A hash-pinnelt fájl sorvégei — a legnehezebben kideríthető pin-bukás.

    ⚠ **Ezt egy valódi bukás hozta elő.** A `core.autocrlf=true` beállítású
    gépeken a git a klónozásnál `LF → CRLF`-re fordít, amitől a fájl **bájtjai**
    megváltoznak, és a pin **elbukik — pedig a tartalom változatlan**. A hiba
    forrása ilyenkor nem is a repóban van, hanem a gép beállításában.

    A puszta pin-bukás üzenete („a séma hashe elcsúszott") ilyenkor **félrevezet**:
    a fejlesztő a sémát fogja keresni, pedig a sorvégeket kell. Ez a teszt ezért
    nem újat mér, hanem a **hibaüzenetet teszi használhatóvá** — a QUALITY §8
    tool-ergonómia elve: *a hibaüzenet mondja meg a következő lépést.*
    """

    def test_a_sema_CSAK_LF_sorvegeket_tartalmaz(self) -> None:
        crlf = SCHEMA_PATH.read_bytes().count(b"\r\n")
        self.assertEqual(
            crlf,
            0,
            f"a sema {crlf} CRLF sorveget tartalmaz. A hash-pin BAJT-szintu, tehat "
            f"ez elbuktatja a pint, pedig a TARTALOM valtozatlan. Valoszinu ok: "
            f"`git config core.autocrlf=true` + hianyzo `.gitattributes` bejegyzes. "
            f"Javitas: a repo `.gitattributes`-eben legyen `contracts/** -text`, "
            f"majd binaris ujramasolas.",
        )

    def test_a_pin_es_a_minta_is_CSAK_LF(self) -> None:
        minta = sorted((REPO / "contracts" / "samples").glob("*.json"))
        self.assertTrue(minta, "nincs aranypeldany — a meres vakon zold lenne")
        for path in (PIN_PATH, *minta):
            with self.subTest(fajl=path.name):
                self.assertEqual(path.read_bytes().count(b"\r\n"), 0)

    def test_a_kapu_HARAP_negativ_kontroll(self) -> None:
        self.assertEqual(b'{"a": 1}' + b"\r\n", b'{"a": 1}' + b"\r\n")
        self.assertEqual((b'{"a": 1}' + b"\r\n").count(b"\r\n"), 1)
        self.assertEqual((b'{"a": 1}' + b"\n").count(b"\r\n"), 0)


if __name__ == "__main__":
    unittest.main()
