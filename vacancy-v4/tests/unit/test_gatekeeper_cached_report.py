import unittest
from app.gatekeeper_cached_report import enrich_snapshot


class CachedReportTests(unittest.TestCase):
    def test_feedback_join_preserves_all_matches(self):
        snapshot = {"provenance": {"source_run_id": 37793929445},
                    "matches": [{"source": "Wise", "job_id": "123"},
                                {"source": "Mollie", "job_id": "456"}]}
        feedback = [{"source": "employer::Wise", "job_id": "123",
                     "label": "not_relevant", "message_id": "a", "received_at": "2026-10-07T08:00:00Z"},
                    {"source": "Wise", "job_id": "123",
                     "label": "relevant", "message_id": "b", "received_at": "2026-10-07T09:00:00Z"}]
        result = enrich_snapshot(snapshot, feedback)
        self.assertEqual(len(result["matches"]), 2)
        self.assertEqual(result["matches"][0]["feedback_status"], "relevant")
        self.assertEqual(len(result["matches"][0]["feedback_history"]), 2)
        self.assertEqual(result["matches"][1]["feedback_status"], "no_feedback")

    def test_duplicate_job_rejected(self):
        snapshot = {"provenance": {}, "matches": [{"source": "Wise", "job_id": "123"}] * 2}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            enrich_snapshot(snapshot, [])


if __name__ == "__main__":
    unittest.main()
