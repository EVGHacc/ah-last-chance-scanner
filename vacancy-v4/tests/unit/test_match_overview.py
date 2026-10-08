import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.match_overview import build_overview, markdown_report


def sample():
    return {"generated_at": "2026-10-08T14:42:49Z", "provider_reports": 4,
            "degraded": True, "unique_matches": 1,
            "matches": [{"source": "Wise", "job_id": "abc123", "employer": "Wise",
                         "title": "Head of Compliance", "location": "Amsterdam",
                         "score": 9, "url": "https://jobs.example.com/abc123"}]}


class MatchOverviewTests(unittest.TestCase):
    def test_feedback_history_and_no_unverified_delivery_claim(self):
        feedback = [
            {"source": "employer::Wise", "job_id": "abc123", "label": "relevant",
             "received_at": "2026-10-07T10:00:00Z", "message_id": "1"},
            {"source": "Wise", "job_id": "abc123", "label": "too_junior",
             "received_at": "2026-10-07T11:00:00Z", "message_id": "2"},
        ]
        result = build_overview(sample(), feedback)
        row = result["matches"][0]
        self.assertEqual(row["feedback"], "too_junior")
        self.assertEqual(len(row["feedback_history"]), 2)
        self.assertEqual(row["notification_status"], "unverified")
        self.assertEqual(row["live_link_status"], "not_checked")
        self.assertEqual(result["coverage_status"], "partial")
        self.assertIn("Head of Compliance", markdown_report(result))

    def test_duplicate_identity_fails_closed(self):
        snapshot = sample()
        snapshot["matches"].append(dict(snapshot["matches"][0]))
        snapshot["unique_matches"] = 2
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_overview(snapshot, [])

    def test_missing_or_untrusted_link_fails_closed(self):
        snapshot = sample()
        snapshot["matches"][0]["url"] = "http://example.com/job"
        with self.assertRaisesRegex(ValueError, "invalid vacancy link"):
            build_overview(snapshot, [])

    def test_inconsistent_match_count_fails_closed(self):
        snapshot = sample()
        snapshot["unique_matches"] = 2
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            build_overview(snapshot, [])


if __name__ == "__main__":
    unittest.main()
