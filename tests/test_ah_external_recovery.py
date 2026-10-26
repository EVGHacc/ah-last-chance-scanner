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
            "latestValid": {
                "authMode": "user-refresh",
                "checkedAt": "2026-10-11T17:58:00+02:00",
            },
        }

    def test_healthy_does_not_dispatch(self):
        self.assertEqual(recovery.decision(self.now, self.good, []), "healthy")

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
