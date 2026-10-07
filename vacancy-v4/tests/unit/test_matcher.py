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

    def test_technical_feedback_penalizes_similar_future_job(self):
        job={"job_id":"new","title":"Compliance Technology Lead","location":"London","summary":"Technical engineering controls for AML compliance","apply_url":"https://example/jobs/new"}
        base=score_job("Wise",job).score
        rows=[{"source":"Wise","job_id":"old","label":"too_technical"}]
        self.assertEqual(score_job("Wise",job,source="Wise",feedback_records=rows).score,base-1)

    def test_technical_feedback_does_not_penalize_nontechnical_job(self):
        job={"job_id":"new2","title":"Compliance Director","location":"London","summary":"AML sanctions governance","apply_url":"https://example/jobs/new2"}
        base=score_job("Wise",job).score
        rows=[{"source":"Wise","job_id":"old","label":"too_technical"}]
        self.assertEqual(score_job("Wise",job,source="Wise",feedback_records=rows).score,base)

    def test_no_management_feedback_penalizes_future_ic_role(self):
        job={"job_id":"new3","title":"Compliance Officer","location":"London","summary":"AML sanctions governance","apply_url":"https://example/jobs/new3"}
        base=score_job("Wise",job).score
        rows=[{"source":"Wise","job_id":"old","label":"no_management_role"}]
        adjusted=score_job("Wise",job,source="Wise",feedback_records=rows)
        self.assertEqual(adjusted.score,base-2)
        self.assertIn("feedback: non-management roles",adjusted.mismatch)

    def test_domain_feedback_requires_persisted_feature_overlap(self):
        job={"job_id":"new4","title":"Scheme Compliance Director","location":"London","summary":"payment scheme compliance governance","apply_url":"https://example/jobs/new4"}
        base=score_job("Wise",job).score
        rows=[{"source":"Wise","job_id":"old","label":"insufficient_experience","features":{"domains":["compliance"]}}]
        self.assertEqual(score_job("Wise",job,source="Wise",feedback_records=rows).score,base-1)

    def test_positive_domain_feedback_prevents_negative_domain_generalisation(self):
        job={"job_id":"new5","title":"Compliance Director","location":"London","summary":"AML compliance governance","apply_url":"https://example/jobs/new5"}
        base=score_job("Wise",job).score
        rows=[
            {"source":"Wise","job_id":"bad","label":"not_relevant","features":{"domains":["compliance"]}},
            {"source":"Wise","job_id":"good","label":"relevant","features":{"domains":["compliance"]}},
        ]
        self.assertEqual(score_job("Wise",job,source="Wise",feedback_records=rows).score,base)

    def test_irrelevant_role_is_not_reported(self):
        job={"job_id":"5","title":"Account Executive","location":"London","summary":"Enterprise sales","apply_url":"https://example/jobs/5"}
        self.assertEqual(rank_inventory("Stripe",[job]),[])

if __name__=="__main__": unittest.main()
