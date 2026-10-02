import sys
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.model import Coverage, Source
from app.runner import ASHBY_MAX_BYTES, ashby_fetch_json, ashby_proof

class RunnerDeveloperTests(unittest.TestCase):
    @patch("app.runner.ashby_inventory", return_value=("a","b"))
    def test_complete_payload_proof(self, _):
        source=Source("employer","Example","example.com",("https://example.com/jobs",))
        proof=ashby_proof(source,"Example")
        self.assertEqual(proof.coverage,Coverage.VERIFIED_COMPLETE)
        self.assertEqual(proof.unique_jobs,2)
        self.assertTrue(proof.exhausted)
        proof.validate()

    @patch("app.runner.fetch_json", return_value={"apiVersion":"1","jobs":[]})
    def test_ashby_transport_has_explicit_large_payload_cap(self, fetch):
        ashby_fetch_json("https://api.ashbyhq.com/posting-api/job-board/openai")
        fetch.assert_called_once_with(
            "https://api.ashbyhq.com/posting-api/job-board/openai",
            max_bytes=ASHBY_MAX_BYTES,
        )
        self.assertEqual(ASHBY_MAX_BYTES,64_000_000)

if __name__=="__main__": unittest.main()
