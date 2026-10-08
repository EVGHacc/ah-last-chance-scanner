import io
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.notifications import Notification
from app.resend_dispatch import submit_strong_match, DispatchError


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"id":"evt-123"}'


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.event = Notification("source:job-1", "job.strong_match", {
            "ROLE": "Head of AML", "SCORE": 9, "SOURCE_URL": "https://example.com/jobs/1"
        })

    def test_event_submitted_without_direct_email(self):
        captured = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["body"] = json.loads(request.data)
            captured["authorization"] = request.get_header("Authorization")
            return FakeResponse()

        event_id = submit_strong_match(
            self.event, api_key="test-token", contact_email="test@example.com", opener=opener
        )
        self.assertEqual(event_id, "evt-123")
        self.assertEqual(captured["url"], "https://api.resend.com/events")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["body"]["event"], "job.strong_match")
        self.assertEqual(captured["body"]["payload"]["SCORE"], 9)
        self.assertEqual(captured["authorization"], "Bearer test-token")

    def test_rejects_missing_credentials_and_wrong_event(self):
        with self.assertRaises(ValueError):
            submit_strong_match(self.event, api_key="", contact_email="test@example.com")
        with self.assertRaises(ValueError):
            submit_strong_match(
                Notification("x", "other.event", {}), api_key="token", contact_email="test@example.com"
            )

    def test_ambiguous_network_failure_is_not_reported_as_success(self):
        from urllib.error import URLError
        def broken(request, timeout):
            raise URLError("timeout")
        with self.assertRaises(DispatchError):
            submit_strong_match(
                self.event, api_key="token", contact_email="test@example.com", opener=broken
            )


if __name__ == "__main__":
    unittest.main()
