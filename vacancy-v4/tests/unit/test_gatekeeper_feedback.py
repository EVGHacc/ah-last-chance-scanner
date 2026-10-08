import unittest
from app.gatekeeper_feedback import history_for_job


class FeedbackJoinTests(unittest.TestCase):
    def test_prefixed_and_plain_sources_merge_without_losing_history(self):
        feedback = [
            {"source": "employer::Wise", "job_id": "123", "label": "not_relevant", "received_at": "2026-10-07T08:35:00Z", "message_id": "a"},
            {"source": "Wise", "job_id": "123", "label": "too_technical", "received_at": "2026-10-07T08:42:00Z", "message_id": "b"},
            {"source": "Wise", "job_id": "123", "label": "duplicate", "received_at": "2026-10-07T08:43:00Z", "message_id": "b"},
            {"source": "Wise", "job_id": "124", "label": "wrong_job", "received_at": "2026-10-07T08:44:00Z", "message_id": "c"},
            {"source": "Other", "job_id": "123", "label": "wrong_source", "received_at": "2026-10-07T08:45:00Z", "message_id": "d"},
        ]
        result = history_for_job(feedback, "Wise", "123")
        self.assertEqual([x["label"] for x in result], ["not_relevant", "too_technical"])
        self.assertEqual(result, history_for_job(feedback, "employer::Wise", "123"))

    def test_malformed_rows_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "feedback row"):
            history_for_job([None], "Wise", "123")


if __name__ == "__main__":
    unittest.main()
