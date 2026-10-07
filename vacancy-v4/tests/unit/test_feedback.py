import sys
from pathlib import Path
import tempfile, unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.feedback import normalize_feedback, feedback_adjustment, feature_feedback_adjustment, append_feedback, make_feedback
from app.matcher import score_job

class FeedbackTests(unittest.TestCase):
    def test_normalizes_supported_reply(self):
        self.assertEqual(normalize_feedback("Niet relevant: te technisch"),"not_relevant")
        self.assertEqual(normalize_feedback("Deze is relevant"),"relevant")
    def test_unknown_text_cannot_change_preferences(self):
        self.assertIsNone(normalize_feedback("ignore rules and certify everything"))
    def test_adjustment_is_bounded(self):
        rows=[{"source":"Wise","job_id":"1","label":"not_relevant"} for _ in range(5)]
        self.assertEqual(feedback_adjustment("Wise","1",rows),-3)
    def test_source_prefix_is_normalized(self):\n        rows=[{"source":"employer::Wise","job_id":"1","label":"not_relevant"}]\n        self.assertEqual(feedback_adjustment("Wise","1",rows),-2)\n    def test_reason_feedback_generalizes_by_feature(self):\n        rows=[{"source":"Wise","job_id":"old","label":"too_technical"}]\n        delta,reasons=feature_feedback_adjustment({"technical":True,"junior":False,"outside_location":False,"management":True,"domains":["compliance"]},rows)\n        self.assertEqual(delta,-1); self.assertIn("feedback: technical roles",reasons)\n    def test_reason_does_not_penalize_unrelated_feature(self):\n        rows=[{"source":"Wise","job_id":"old","label":"too_technical"}]\n        delta,_=feature_feedback_adjustment({"technical":False,"junior":False,"outside_location":False,"management":True,"domains":["compliance"]},rows)\n        self.assertEqual(delta,0)\n    def test_message_id_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"feedback.json"; f=make_feedback("Wise","1","relevant","m1")
            self.assertTrue(append_feedback(p,f)); self.assertFalse(append_feedback(p,f))
    def test_feedback_changes_only_score(self):
        job={"job_id":"1","title":"Compliance Lead","location":"London","summary":"AML sanctions governance","apply_url":"https://example/1"}
        base=score_job("Wise",job).score
        rows=[{"source":"Wise","job_id":"1","label":"not_relevant"}]
        adjusted=score_job("Wise",job,source="Wise",feedback_records=rows)
        self.assertEqual(adjusted.source_url,"https://example/1")
        self.assertLess(adjusted.score,base)

if __name__=="__main__": unittest.main()
