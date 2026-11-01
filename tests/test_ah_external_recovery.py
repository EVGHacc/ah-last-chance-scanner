"""Regression tests for independent AH recovery and its workflow entrypoint."""
import importlib.util
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("external_recovery", ROOT / "scripts/external_start_recovery.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class ExternalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 11, 18, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
        self.good = {
            "date": "2026-10-11", "authMode": "user-refresh", "category": "Vlees",
            "rawExpected": 101, "canonicalExpected": 61,
            "stores": [1463, 1348, 1135],
            "rawSeen": sorted(recovery.expected_slots(3)),
            "canonicalSeen": sorted(recovery.expected_slots(5)),
            "rawMissing": [], "canonicalMissing": [],
            "latestValid": {
                "authMode": "user-refresh",
                "checkedAt": "2026-10-11T17:58:00+02:00",
            },
        }

    def test_healthy_requires_complete_raw_and_canonical_day(self):
        self.assertEqual(recovery.decision(self.now, self.good, []), "healthy")

    def test_incomplete_raw_slots_are_not_healthy(self):
        status = {**self.good, "rawSeen": self.good["rawSeen"][:-1]}
        self.assertEqual(recovery.decision(self.now, status, []), "dispatch")

    def test_incomplete_canonical_slots_are_not_healthy(self):
        status = {**self.good, "canonicalSeen": self.good["canonicalSeen"][:-1]}
        self.assertEqual(recovery.decision(self.now, status, []), "dispatch")

    def test_duplicate_slot_cannot_fake_complete_count(self):
        slots = self.good["rawSeen"][:-1] + [self.good["rawSeen"][0]]
        status = {**self.good, "rawSeen": slots}
        self.assertEqual(recovery.decision(self.now, status, []), "dispatch")

    def test_malformed_slot_values_are_not_healthy(self):
        status = {**self.good, "rawSeen": [None] * 101}
        self.assertEqual(recovery.decision(self.now, status, []), "dispatch")

    def test_missing_heartbeat_dispatches(self):
        self.assertEqual(recovery.decision(self.now, {}, []), "dispatch")

    def test_wrong_category_dispatches(self):
        self.assertEqual(recovery.decision(self.now, {**self.good, "category": "Vleeswaren"}, []), "dispatch")

    def test_active_run_prevents_duplicate(self):
        runs = [{"event": "workflow_dispatch", "status": "in_progress",
                 "created_at": "2026-10-11T15:59:00Z"}]
        self.assertEqual(recovery.decision(self.now, {}, runs), "active-run")

    def test_recent_completed_run_cooldown(self):
        runs = [{"event": "workflow_dispatch", "status": "completed",
                 "created_at": "2026-10-11T15:59:00Z"}]
        self.assertEqual(recovery.decision(self.now, {}, runs), "cooldown")

    def test_outside_window(self):
        late = datetime(2026, 10, 11, 23, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
        self.assertEqual(recovery.decision(late, {}, []), "outside-window")


if __name__ == "__main__":
    unittest.main()
