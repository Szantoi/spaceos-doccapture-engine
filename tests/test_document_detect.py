"""Az irat-típus felismerése — bizonyítékkal, és holtversenynél HALLGATVA.

A legfontosabb teszt itt nem az, hogy megtalálja a helyes profilt, hanem hogy
**nem dönt**, amikor nem tudja. Egy rossz profil nem egy mezőt ront el, hanem az
**egész elemzést** — és úgy néz ki, mint egy sikeres feldolgozás.
"""

from __future__ import annotations

import unittest

from doccapture.core.documents import DocumentProfile, FieldSpec, detect_profile, normalize_text
from doccapture.core.errors import ConfigurationError
from doccapture.core.models import Confidence, SourceEvidence

BIZONYLAT = DocumentProfile(
    profile_id="bizonylat",
    required_anchors=("bizonylat",),
    optional_anchors=("adóalap", "végösszeg"),
    fields=(FieldSpec("szam", ("Bizonylatszám",)),),
)
MUNKALAP = DocumentProfile(
    profile_id="munkalap",
    required_anchors=("munkalap",),
    optional_anchors=("munkaszám", "gépidő"),
    fields=(FieldSpec("szam", ("Munkaszám",)),),
)
KATALOGUS = (BIZONYLAT, MUNKALAP)


class UnambiguousTests(unittest.TestCase):
    def test_egy_illeszkedo_profil_MEGBIZHATO(self) -> None:
        result = detect_profile(["Munkalap", "Munkaszám: 123", "Gépidő: 4"], KATALOGUS)

        self.assertEqual(result.profile.value, "munkalap")
        self.assertIs(result.profile.confidence, Confidence.CONFIRMED)
        self.assertIs(result.selected, MUNKALAP)

    def test_a_pontszam_DARABSZAM_nem_valoszinuseg(self) -> None:
        """Nem osztályozó: a pontszám a megtalált bizonyítékok száma."""
        result = detect_profile(["Munkalap", "Munkaszám: 1", "Gépidő: 2"], KATALOGUS)
        match = next(m for m in result.candidates if m.profile is MUNKALAP)
        self.assertEqual(match.score, 3)  # 1 kotelezo + 2 opcionalis

    def test_a_bizonyitek_atkerul_a_felismeresre(self) -> None:
        evidence = SourceEvidence("irat.txt", "sha256:abc")
        result = detect_profile(["Munkalap"], KATALOGUS, evidence)
        self.assertIs(result.profile.evidence, evidence)


class RefusalTests(unittest.TestCase):
    """Ahol NEM döntünk — és miért ez a helyes válasz."""

    def test_a_HOLTVERSENY_hianyt_ad_nem_valasztast(self) -> None:
        """Mindkét profil 1-1 horgonnyal illeszkedik. Ha választanánk, az egész
        elemzés rossz lenne, és sikeresnek látszana."""
        result = detect_profile(["Munkalap és bizonylat egy lapon"], KATALOGUS)

        self.assertIsNone(result.profile.value)
        self.assertIs(result.profile.confidence, Confidence.MISSING)
        self.assertIn("holtverseny", result.profile.note)
        self.assertIn("bizonylat", result.profile.note)
        self.assertIn("munkalap", result.profile.note)
        self.assertIsNone(result.selected)

    def test_egyetlen_illeszkedes_sem_HIANY_nem_hiba(self) -> None:
        """A „nem tudom, milyen irat" ÉRVÉNYES válasz — nem kivétel."""
        result = detect_profile(["Valamilyen teljesen más szöveg"], KATALOGUS)

        self.assertIsNone(result.profile.value)
        self.assertIs(result.profile.confidence, Confidence.MISSING)
        self.assertIn("emberi besorolás", result.profile.note)

    def test_ures_katalogussal_is_hianyt_ad_nem_szall_el(self) -> None:
        result = detect_profile(["Munkalap"], ())
        self.assertIs(result.profile.confidence, Confidence.MISSING)


class TieBreakTests(unittest.TestCase):
    def test_a_TOBB_bizonyitek_nyer_de_JELOLVE(self) -> None:
        """Ha van szigorúan legjobb, döntünk — de az ember nézze meg."""
        result = detect_profile(
            ["Munkalap és bizonylat", "Munkaszám: 1", "Gépidő: 2"], KATALOGUS
        )

        self.assertEqual(result.profile.value, "munkalap")
        self.assertIs(result.profile.confidence, Confidence.NEEDS_REVIEW)
        self.assertIn("több profil", result.profile.note)

    def test_a_KOTELEZO_horgony_hianya_kizar(self) -> None:
        """Nem pontlevonás: kizárás. Egy kötelező horgony nélkül a profil nem jelölt."""
        result = detect_profile(["Adóalap: 100", "Végösszeg: 127"], KATALOGUS)
        match = next(m for m in result.candidates if m.profile is BIZONYLAT)

        self.assertFalse(match.eligible)
        self.assertEqual(match.missing_required, ("bizonylat",))
        self.assertEqual(match.score, 2, "az opcionalis horgonyok megvoltak")
        self.assertIsNone(result.profile.value, "megis nem valasztottuk ki")


class ExplainabilityTests(unittest.TestCase):
    """Egy „miért ezt választotta?" kérdésre válaszolni kell tudni."""

    def test_a_diagnosztika_MINDEN_jeloltet_felsorol(self) -> None:
        result = detect_profile(["Munkalap", "Munkaszám: 1"], KATALOGUS)
        egyben = "\n".join(result.diagnostics)

        self.assertIn("2 profil megvizsgálva", egyben)
        self.assertIn("munkalap", egyben)
        self.assertIn("bizonylat", egyben)
        self.assertIn("kizárva", egyben)

    def test_a_mérleg_a_KIZART_profilrol_is_beszel(self) -> None:
        result = detect_profile(["Munkalap"], KATALOGUS)
        egyben = "\n".join(result.diagnostics)
        self.assertIn("hiányzó kötelező", egyben)


class NormalizationTests(unittest.TestCase):
    def test_az_EKEZET_hajtogatas_itt_BE_van_kapcsolva(self) -> None:
        """Szemben a táblázat fejléc-illesztésével — és a különbség indokolt:
        itt a szöveg FELISMERÉSBŐL jön, ahol az ékezet a leggyakoribb hibaforrás.
        Ha nem hajtogatnánk, egy hibás ékezet miatt a TELJES iratot nem ismernénk fel."""
        self.assertEqual(normalize_text("Gépidő"), normalize_text("Gepido"))
        result = detect_profile(["Munkalap", "Gepido: 4"], KATALOGUS)
        match = next(m for m in result.candidates if m.profile is MUNKALAP)
        self.assertIn("gépidő", match.matched_optional)

    def test_a_kisbetu_es_a_szokoz_szamok_nem_zavarnak(self) -> None:
        self.assertEqual(normalize_text("  MUNKA   LAP \n"), "munka lap")


class ProfileValidationTests(unittest.TestCase):
    """A profil-leírás hibája a MI hibánk → `ConfigurationError`."""

    def test_horgony_nelkuli_profil_MINDEN_iratra_illeszkedne(self) -> None:
        with self.assertRaises(ConfigurationError) as ctx:
            DocumentProfile(profile_id="rossz", fields=(FieldSpec("a", ("A",)),))
        self.assertIn("MINDEN iratra", str(ctx.exception))

    def test_ures_azonosito(self) -> None:
        with self.assertRaises(ConfigurationError):
            DocumentProfile(profile_id="", required_anchors=("x",))

    def test_ismetlodo_mezo_kulcs(self) -> None:
        with self.assertRaises(ConfigurationError):
            DocumentProfile(
                profile_id="p",
                required_anchors=("x",),
                fields=(FieldSpec("a", ("A",)), FieldSpec("a", ("B",))),
            )

    def test_cimke_nelkuli_mezo_soha_nem_lenne_megtalalhato(self) -> None:
        with self.assertRaises(ConfigurationError):
            FieldSpec("a", ())


if __name__ == "__main__":
    unittest.main()
