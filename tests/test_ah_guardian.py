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
             patch.object(guardian.session, "final_reconcile", return_value=False) as reconcile:
            with self.assertRaises(SystemExit) as raised:
                guardian.main()

        self.assertEqual(raised.exception.code, 1)
        reconcile.assert_called_once()

    def test_successful_final_reconciliation_returns_normally(self):
        with patch.object(guardian, "prestart_readiness"), \
             patch.object(guardian.session, "points_for", return_value=[]), \
             patch.object(guardian.session, "final_reconcile", return_value=True) as reconcile:
            self.assertIsNone(guardian.main())

        reconcile.assert_called_once()


if __name__ == "__main__":
    unittest.main()
