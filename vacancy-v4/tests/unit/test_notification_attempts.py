import tempfile
import unittest
from pathlib import Path
from app.notification_attempts import claim_attempt,load_attempts


class NotificationAttemptTests(unittest.TestCase):
    def test_duplicate_claim_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"receipts.json"
            claim_attempt(path,"bank:job-1")
            with self.assertRaises(ValueError):
                claim_attempt(path,"bank:job-1")

    def test_claim_is_durable(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'receipts.json'
            claim_attempt(path,'source:job')
            self.assertEqual(load_attempts(path)['source:job']['status'],'in_flight')

    def test_corrupted_pending_ledger_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"receipts.json"
            pending=path.with_name(path.name+".pending.json")
            pending.write_text("[]")
            with self.assertRaises(ValueError):
                load_attempts(path)
