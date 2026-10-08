import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.matcher import Match
from app.notify_runner import dispatch_new_matches
from app.notifications import load_receipts


class NotifyRunnerTests(unittest.TestCase):
    def test_sends_once_across_repeated_batches(self):
        match = Match("Bank", "job-1", "Head of Compliance", "London",
                      "https://example.com/jobs/1", 9, ("compliance",), (), ())
        calls = []

        def submit(notification, **kwargs):
            calls.append(notification.key)
            return "evt-123"

        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "receipts.json"
            jobs = [("bank", match), ("bank", match)]
            self.assertEqual(len(dispatch_new_matches(
                jobs, receipt_path=ledger, api_key="token",
                contact_email="test@example.com", submit=submit
            )), 1)
            self.assertEqual(dispatch_new_matches(
                jobs, receipt_path=ledger, api_key="token",
                contact_email="test@example.com", submit=submit
            ), [])
            self.assertEqual(calls, ["bank:job-1"])
            self.assertIn("bank:job-1", load_receipts(ledger))

    def test_failed_submission_does_not_record_receipt(self):
        match = Match("Bank", "job-2", "Head of Risk", "London",
                      "https://example.com/jobs/2", 9, ("risk",), (), ())

        def submit(notification, **kwargs):
            raise RuntimeError("provider unavailable")

        with tempfile.TemporaryDirectory() as folder:
            ledger = Path(folder) / "receipts.json"
            with self.assertRaises(RuntimeError):
                dispatch_new_matches(
                    [("bank", match)], receipt_path=ledger, api_key="token",
                    contact_email="test@example.com", submit=submit
                )
            self.assertEqual(load_receipts(ledger), {})


if __name__ == "__main__":
    unittest.main()
