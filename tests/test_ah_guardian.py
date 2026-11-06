import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import guardian


class GuardianReadOnlyTests(unittest.TestCase):
    def test_missing_point_is_reported_without_scan_retry_or_checkout(self):
        target = datetime(2026, 10, 2, 17, 30, tzinfo=guardian.TZ)
        with patch.object(guardian, "wait_until"), \
             patch.object(guardian.session, "point_complete", side_effect=[False, False]), \
             patch.object(guardian.time, "sleep"), \
             patch.object(guardian.session, "run_point") as run_point, \
             patch.object(guardian.session, "refresh_checkout") as refresh:
            self.assertFalse(guardian.guard_point(target))

        run_point.assert_not_called()
        refresh.assert_not_called()

    def test_second_read_can_confirm_primary_publication(self):
        target = datetime(2026, 10, 2, 17, 30, tzinfo=guardian.TZ)
        with patch.object(guardian, "wait_until"), \
             patch.object(guardian.session, "point_complete", side_effect=[False, True]), \
             patch.object(guardian.time, "sleep"):
            self.assertTrue(guardian.guard_point(target))

    def test_failed_final_reconciliation_exits_nonzero(self):
        with patch.object(guardian, "prestart_readiness"), \
             patch.object(guardian.session, "points_for", return_value=[]), \
             patch.object(guardian, "final_reconcile", return_value=False):
            with self.assertRaises(SystemExit) as raised:
                guardian.main()

        self.assertEqual(raised.exception.code, 1)

    def test_successful_final_reconciliation_returns_normally(self):
        with patch.object(guardian, "prestart_readiness"), \
             patch.object(guardian.session, "points_for", return_value=[]), \
             patch.object(guardian, "final_reconcile", return_value=True):
            self.assertIsNone(guardian.main())

    def test_final_reconcile_fails_when_any_expected_slot_is_missing(self):
        today = datetime(2026, 10, 2, tzinfo=guardian.TZ)
        with patch.object(guardian.session, "points_for", return_value=[
            datetime(2026, 10, 2, 17, 30, tzinfo=guardian.TZ)
        ]), patch.object(guardian.session, "status_seen", return_value=(set(), set())):
            self.assertFalse(guardian.final_reconcile(today))


if __name__ == "__main__":
    unittest.main()
