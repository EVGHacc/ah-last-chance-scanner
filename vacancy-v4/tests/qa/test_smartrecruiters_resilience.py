import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.smartrecruiters_batch import run_batch

class SmartRecruitersIndependentQA(unittest.TestCase):
    def test_network_failure_is_fail_closed(self):
        def fetch(url): raise RuntimeError("simulated network failure")
        r=run_batch(fetch)
        self.assertEqual((r["verified_complete"],r["failed"]),(0,1))
        self.assertEqual(r["sources"][0]["jobs"],[])
        self.assertIn("network failure",r["sources"][0]["error"])
    def test_malformed_payload_is_not_coverage(self):
        r=run_batch(lambda url:{"unexpected":[]})
        self.assertEqual(r["sources"][0]["coverage"],"unproven")
        self.assertEqual(r["sources"][0]["unique_jobs"],0)
if __name__=="__main__":unittest.main()
