import tempfile
import unittest
from pathlib import Path
from app.notification_attempts import claim_attempt,load_attempts

class RetryTests(unittest.TestCase):
    def test_unresolved_claim_survives_process_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"receipts.json"
            claim_attempt(path,"source:job")
            self.assertEqual(load_attempts(path)["source:job"]["status"],"in_flight")
            with self.assertRaises(ValueError):
                claim_attempt(path,"source:job")
