import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import guardian


class GuardianExitStatusTests(unittest.TestCase):
    def test_failed_final_reconciliation_exits_nonzero(self):
        with patch.object(guardian, "prestart_readiness"), \
             patch.object(guardian.session, "points_for", return_value=[]), \
             patch.object(guardian.session, "reconcile_publication", return_value=False) as reconcile:
            with self.assertRaises(SystemExit) as raised:
                guardian.main()

        self.assertEqual(raised.exception.code, 1)
        reconcile.assert_called_once()

    def test_guardian_final_reconciliation_is_strictly_read_only(self):
        with patch.object(guardian, "prestart_readiness"), \
             patch.object(guardian.session, "points_for", return_value=[]), \
             patch.object(guardian.session, "reconcile_publication", return_value=True), \
             patch.object(guardian.session, "refresh_checkout") as refresh:
            guardian.main()

        refresh.assert_not_called()

    def test_missing_slot_never_triggers_guardian_recovery(self):
        target = guardian.datetime(2026, 10, 2, 17, 30, tzinfo=guardian.TZ)
        with (
            patch.object(guardian, "wait_until"),
            patch.object(guardian.session, "point_complete", return_value=False),
            patch.object(guardian.session, "run_point") as run_point,
        ):
            self.assertFalse(guardian.guard_point(target))
        run_point.assert_not_called()

    def test_successful_final_reconciliation_returns_normally(self):
        with patch.object(guardian, "prestart_readiness"), \
             patch.object(guardian.session, "points_for", return_value=[]), \
             patch.object(guardian.session, "reconcile_publication", return_value=True) as reconcile:
            self.assertIsNone(guardian.main())

        reconcile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
