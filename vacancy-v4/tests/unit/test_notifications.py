import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.matcher import Match
from app.notifications import prepare_strong_match, load_receipts, record_accepted_event


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.match = Match("Example Bank", "job-1", "Head of AML", "Amsterdam",
                           "https://example.com/jobs/1", 9, ("aml",), (), ())

    def test_valid_payload_has_numeric_score_and_existing_event(self):
        result = prepare_strong_match(self.match, "bank", set())
        self.assertEqual(result.event, "job.strong_match")
        self.assertEqual(result.key, "bank:job-1")
        self.assertIsInstance(result.payload["SCORE"], int)
        self.assertEqual(result.payload["SCORE"], 9)

    def test_sent_match_is_suppressed(self):
        self.assertIsNone(prepare_strong_match(self.match, "bank", {"bank:job-1"}))

    def test_invalid_or_untrusted_link_is_suppressed(self):
        from dataclasses import replace
        for url in ("", "http://example.com/job", "javascript:alert(1)",
                    "https://name:pass@example.com/job"):
            self.assertIsNone(prepare_strong_match(replace(self.match, source_url=url), "bank", set()))

    def test_receipt_roundtrip_and_duplicate_rejection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sent.json"
            notification = prepare_strong_match(self.match, "bank", set())
            self.assertEqual(load_receipts(path), {})
            record_accepted_event(path, notification, "evt-123")
            receipts = load_receipts(path)
            self.assertEqual(receipts["bank:job-1"]["event_id"], "evt-123")
            self.assertIsNone(prepare_strong_match(self.match, "bank", set(receipts)))
            with self.assertRaises(ValueError):
                record_accepted_event(path, notification, "evt-456")

    def test_corrupt_receipts_fail_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sent.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_receipts(path)

    def test_non_strong_match_is_suppressed(self):
        from dataclasses import replace
        self.assertIsNone(prepare_strong_match(replace(self.match, score=6), "bank", set()))


if __name__ == "__main__":
    unittest.main()
