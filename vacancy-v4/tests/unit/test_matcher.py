import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.matcher import rank_inventory, score_job

class MatcherTests(unittest.TestCase):
    def test_fincrime_head_is_strong_even_with_nonstandard_title(self):
        job={"job_id":"1","title":"Head of Financial Crime Control Governance","location":"London",
             "summary":"Own AML, sanctions, controls and regulatory governance.","apply_url":"https://example/jobs/1"}
        m=score_job("Wise",job)
        self.assertGreaterEqual(m.score,9)
        self.assertTrue(m.strong)

    def test_description_can_make_generic_title_relevant(self):
        job={"job_id":"2","title":"Business Manager","location":"Amsterdam, Netherlands",
             "summary":"Director-level COO role leading regulatory transformation, governance and non-financial risk.",
             "apply_url":"https://example/jobs/2"}
        self.assertGreaterEqual(score_job("MUFG",job).score,7)

    def test_junior_role_is_not_strong(self):
        job={"job_id":"3","title":"Junior Compliance Analyst","location":"Amsterdam",
             "summary":"AML compliance monitoring","apply_url":"https://example/jobs/3"}
        self.assertFalse(score_job("X",job).strong)

    def test_deduplicates_inventory_before_reporting(self):
        job={"job_id":"4","title":"Compliance Senior Manager - EU FinCrime Monitoring & Testing",
             "location":"Amsterdam","summary":"Financial crime AML sanctions","apply_url":"https://example/jobs/4"}
        self.assertEqual(len(rank_inventory("Wise",[job,dict(job)])),1)

    def test_irrelevant_role_is_not_reported(self):
        job={"job_id":"5","title":"Account Executive","location":"London","summary":"Enterprise sales","apply_url":"https://example/jobs/5"}
        self.assertEqual(rank_inventory("Stripe",[job]),[])

if __name__=="__main__": unittest.main()
