"""A két alapszabály tesztje.

Nem azt mérjük, hogy a dataclass működik-e, hanem hogy a modell KIKÉNYSZERÍTI
a szabályokat: bizonytalanságot nem lehet elhallgatni, és értéket nem lehet
kitalálni.
"""

import unittest

from doccapture.core.models import (
    CaptureRecord,
    Confidence,
    Extracted,
    InputKind,
    SourceEvidence,
)

EVIDENCE = SourceEvidence(relative_path="beérkezett/a.pdf", content_hash="abc123")


class ExtractedInvariants(unittest.TestCase):
    def test_missing_cannot_carry_a_value(self) -> None:
        """MISSING mellett érték = valaki tippelt, aztán hiányra állította."""
        with self.assertRaises(ValueError):
            Extracted(value="42", confidence=Confidence.MISSING)

    def test_a_value_less_claim_must_be_missing(self) -> None:
        """Érték nélkül nem állíthatjuk, hogy CONFIRMED — ez a csendes hazugság."""
        with self.assertRaises(ValueError):
            Extracted(value=None, confidence=Confidence.CONFIRMED)

    def test_missing_is_a_valid_answer(self) -> None:
        """A hiány helyes válasz, nem hibaállapot."""
        item = Extracted(value=None, confidence=Confidence.MISSING, note="nem olvasható")
        self.assertIsNone(item.value)


class NeedsHumanRule(unittest.TestCase):
    def test_all_confirmed_needs_no_human(self) -> None:
        record = CaptureRecord(
            input_kind=InputKind.TABULAR,
            evidence=EVIDENCE,
            fields={"total": Extracted(value=10, confidence=Confidence.CONFIRMED)},
        )
        self.assertFalse(record.needs_human)

    def test_one_uncertain_row_flags_the_whole_record(self) -> None:
        """Egyetlen bizonytalan sor is emberi szemet kíván — nem átlagolunk."""
        record = CaptureRecord(
            input_kind=InputKind.RASTER_SCAN,
            evidence=EVIDENCE,
            rows=[
                {"qty": Extracted(value=3, confidence=Confidence.CONFIRMED)},
                {"qty": Extracted(value=7, confidence=Confidence.NEEDS_REVIEW)},
            ],
        )
        self.assertTrue(record.needs_human)

    def test_missing_also_flags(self) -> None:
        record = CaptureRecord(
            input_kind=InputKind.HANDWRITING,
            evidence=EVIDENCE,
            fields={"code": Extracted(value=None, confidence=Confidence.MISSING)},
        )
        self.assertTrue(record.needs_human)


class EvidenceChain(unittest.TestCase):
    def test_evidence_needs_a_content_hash(self) -> None:
        """Útvonal önmagában nem bizonyíték: a fájl tartalma változhat."""
        evidence = SourceEvidence(relative_path="x/y.xlsx", content_hash="deadbeef")
        self.assertTrue(evidence.content_hash)


if __name__ == "__main__":
    unittest.main()
