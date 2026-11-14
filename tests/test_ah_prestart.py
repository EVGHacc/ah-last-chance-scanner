import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import prestart, schedule_gate

TZ = ZoneInfo("Europe/Amsterdam")
ROOT = Path(__file__).resolve().parents[1]


class ScheduleGateTests(unittest.TestCase):
    def test_summer_primary_prestart_cron_is_admitted(self):
        now = datetime(2026, 7, 10, 17, 25, tzinfo=TZ)
        self.assertTrue(schedule_gate.allowed("schedule", "25 15 * * *", now))

    def test_summer_backup_prestart_cron_is_admitted(self):
        now = datetime(2026, 7, 10, 17, 28, tzinfo=TZ)
        self.assertTrue(schedule_gate.allowed("schedule", "28 15 * * *", now))

    def test_winter_backup_prestart_cron_is_admitted(self):
        now = datetime(2026, 11, 2, 17, 28, tzinfo=TZ)
        self.assertTrue(schedule_gate.allowed("schedule", "28 16 * * *", now))

    def test_already_claimed_session_suppresses_backup_trigger(self):
        now = datetime(2026, 11, 2, 17, 28, tzinfo=TZ)
        self.assertEqual(schedule_gate.classify("schedule", "28 16 * * *", now, claimed=True), "claimed")

    def test_winter_primary_prestart_cron_is_admitted(self):
        now = datetime(2026, 11, 2, 17, 25, tzinfo=TZ)
        self.assertTrue(schedule_gate.allowed("schedule", "25 16 * * *", now))

    def test_wrong_cron_and_non_schedule_events_are_rejected(self):
        now = datetime(2026, 11, 2, 17, 25, tzinfo=TZ)
        self.assertFalse(schedule_gate.allowed("schedule", "30 16 * * *", now))
        self.assertFalse(schedule_gate.allowed("workflow_dispatch", "", now))
        self.assertFalse(schedule_gate.allowed("push", "", now))

    def test_active_schedule_later_than_240_seconds_is_classified_late(self):
        late = datetime(2026, 11, 2, 17, 29, 1, tzinfo=TZ)
        self.assertEqual(schedule_gate.classify("schedule", "25 16 * * *", late), "late")

    def test_other_dst_cron_is_explicitly_inactive(self):
        winter = datetime(2026, 11, 2, 16, 25, tzinfo=TZ)
        self.assertEqual(schedule_gate.classify("schedule", "25 15 * * *", winter), "inactive")
        self.assertEqual(schedule_gate.classify("schedule", "28 15 * * *", winter.replace(minute=28)), "inactive")

    def test_schedule_outside_its_prestart_window_is_rejected(self):
        early = datetime(2026, 11, 2, 17, 24, 59, tzinfo=TZ)
        late = datetime(2026, 11, 2, 17, 29, 1, tzinfo=TZ)
        self.assertFalse(schedule_gate.allowed("schedule", "25 16 * * *", early))
        self.assertFalse(schedule_gate.allowed("schedule", "25 16 * * *", late))

    def test_production_workflow_has_both_dst_aware_prestart_schedules(self):
        workflow = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")
        for cron in ("25 15", "25 16", "28 15", "28 16"):
            self.assertIn(f"- cron: '{cron} * * *'", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertNotIn("recovery_confirmation:", workflow)
        self.assertNotIn("git push origin HEAD:main", workflow)
        self.assertIn("GATE_DECISION", workflow)
        self.assertIn("EXPECTED PRESTART MISSED OR INVALID", workflow)
        self.assertIn("python scripts/prestart.py", workflow)
        self.assertIn("Claim today's production session", workflow)
        self.assertIn("actions/cache/restore@v4", workflow)
        self.assertIn("actions/cache/save@v4", workflow)
        self.assertIn("steps.claim_cache_save.outcome == 'success'", workflow)
        self.assertIn("steps.prestart.outcome == 'success' && steps.claim_cache_save.outcome == 'success'", workflow)
        self.assertNotIn("git push origin HEAD:main", workflow)
        self.assertIn("scripts/prestart.py", workflow)
        probe = (ROOT / ".github/workflows/probe.yml").read_text(encoding="utf-8")
        self.assertIn("  pull_request:", probe)
        self.assertIn("test_ah_prestart.py", probe)


class PrestartTests(unittest.TestCase):
    def test_prestart_accepts_present_refresh_token_without_network_probe(self):
        self.assertTrue(prestart.validate_preflight({"AH_REFRESH_TOKEN": "opaque-token"}))

    def test_prestart_rejects_missing_refresh_token(self):
        with self.assertRaisesRegex(RuntimeError, "AH_REFRESH_TOKEN"):
            prestart.validate_preflight({})

    def test_prestart_does_not_require_historical_data(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as empty_dir:
            try:
                os.chdir(empty_dir)
                self.assertTrue(prestart.validate_preflight({"AH_REFRESH_TOKEN": "opaque-token"}))
            finally:
                os.chdir(original)


if __name__ == "__main__":
    unittest.main()
