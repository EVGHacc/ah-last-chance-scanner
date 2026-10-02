import sys
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.model import Coverage, Source
from app.runner import ashby_proof

class RunnerDeveloperTests(unittest.TestCase):
    @patch("app.runner.ashby_inventory", return_value=("a","b"))
    def test_complete_payload_proof(self, _):
        source=Source("employer","Example","example.com",("https://example.com/jobs",))
        proof=ashby_proof(source,"Example")
        self.assertEqual(proof.coverage,Coverage.VERIFIED_COMPLETE)
        self.assertEqual(proof.unique_jobs,2)
        self.assertTrue(proof.exhausted)
        proof.validate()

if __name__=="__main__": unittest.main()
