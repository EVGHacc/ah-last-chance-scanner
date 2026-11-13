"""TDD contracts for the single-owner AH scheduler and read-only watchdog."""
import re
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import session_watchdog


class ProductionWorkflowConcurrencyTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_session_is_the_only_scheduled_production_owner(self):
        session = self.read(".github/workflows/session.yml")
        guardian = self.read(".github/workflows/guardian.yml")
        fallback = self.read(".github/workflows/fallback-qa.yml")

        self.assertIn("  schedule:", session)
        self.assertIn("- cron: '0 21 * * *'", fallback)
        self.assertIn("- cron: '0 22 * * *'", fallback)
        self.assertIn("python scripts/independent_qa.py --complete", fallback)
        self.assertIn("group: ah-production-single-writer", session)
        self.assertIn("cancel-in-progress: false", session)
        self.assertNotIn("  schedule:", guardian)
        self.assertNotIn("workflow_dispatch:", guardian)
        self.assertNotIn("  workflow_dispatch:", fallback)
        self.assertIn("  schedule:", fallback)

    def test_observers_are_read_only_and_never_cancel_or_dispatch(self):
        guardian = self.read(".github/workflows/guardian.yml")
        fallback = self.read(".github/workflows/fallback-qa.yml")
        watchdog = self.read("scripts/session_watchdog.py")

        self.assertIn("contents: read", guardian)
        self.assertIn("contents: read", fallback)
        self.assertNotIn("contents: write", guardian + fallback)
        self.assertNotIn("actions: write", guardian + fallback)
        self.assertNotIn("/cancel", watchdog)
        self.assertNotIn("/dispatches", watchdog)
        self.assertNotIn("method=\"POST\"", watchdog)

    def test_no_production_workflow_cancels_in_progress_work(self):
        for path in (
            ".github/workflows/session.yml",
            ".github/workflows/guardian.yml",
            ".github/workflows/fallback-qa.yml",
        ):
            with self.subTest(path=path):
                self.assertNotIn("cancel-in-progress: true", self.read(path))


class WatchdogDecisionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 18, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
        self.healthy_status = {
            "date": "2026-11-02",
            "authMode": "user-refresh",
            "rawExpected": 101,
            "canonicalExpected": 61,
            "category": "Vlees",
            "stores": [1463, 1348, 1135, 4046, 8728],
            "latestValid": {
                "authMode": "user-refresh",
                "checkedAt": "2026-11-02T17:59:00+01:00",
            },
        }
        self.active_run = [{
            "event": "schedule",
            "status": "in_progress",
            "created_at": "2026-11-02T16:55:00Z",
        }]

    def test_healthy_active_session_is_observed_not_interrupted(self):
        self.assertEqual(
            session_watchdog.decision(self.healthy_status, self.active_run, self.now),
            "HEALTHY",
        )

    def test_missing_active_session_is_alarm_without_recovery_action(self):
        self.assertEqual(
            session_watchdog.decision(self.healthy_status, [], self.now),
            "ALARM",
        )

    def test_stale_scan_is_alarm_even_if_session_run_is_active(self):
        stale = {
            **self.healthy_status,
            "latestValid": {
                **self.healthy_status["latestValid"],
                "checkedAt": "2026-11-02T17:50:00+01:00",
            },
        }
        self.assertEqual(
            session_watchdog.decision(stale, self.active_run, self.now),
            "ALARM",
        )

    def test_after_window_missing_final_publication_is_alarm(self):
        outside = datetime(2026, 11, 2, 23, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
        self.assertEqual(session_watchdog.decision({}, [], outside), "ALARM")

    def test_after_window_duplicate_raw_slot_is_alarm(self):
        outside = datetime(2026, 11, 2, 23, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
        raw = sorted(session_watchdog.expected_slots(3))
        raw[-1] = raw[0]
        status = {
            **self.healthy_status,
            "rawSeen": raw,
            "canonicalSeen": sorted(session_watchdog.expected_slots(5)),
            "rawMissing": [],
            "canonicalMissing": [],
            "latestValid": {
                "authMode": "user-refresh",
                "checkedAt": "2026-11-02T22:33:00+01:00",
            },
        }
        self.assertEqual(session_watchdog.decision(status, [], outside), "ALARM")

    def test_after_window_complete_final_publication_is_complete(self):
        outside = datetime(2026, 11, 2, 23, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
        status = {
            **self.healthy_status,
            "rawSeen": sorted(session_watchdog.expected_slots(3)),
            "canonicalSeen": sorted(session_watchdog.expected_slots(5)),
            "rawMissing": [],
            "canonicalMissing": [],
            "latestValid": {
                "authMode": "user-refresh",
                "checkedAt": "2026-11-02T22:33:00+01:00",
                "rawScheduledSlot": "22:30",
                "status": "OK",
            },
        }
        self.assertEqual(session_watchdog.decision(status, [], outside), "COMPLETE")


if __name__ == "__main__":
    unittest.main()
