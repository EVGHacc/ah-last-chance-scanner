import contextlib
import io
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import session


class SingleAttemptSessionTests(unittest.TestCase):
    def test_failed_scan_is_not_retried_and_stderr_is_suppressed(self):
        target = datetime(2026, 11, 2, 17, 30, tzinfo=ZoneInfo("Europe/Amsterdam"))
        output = io.StringIO()
        failure = SimpleNamespace(returncode=1, stderr="SECRET_REFRESH_TOKEN", stdout="")
        with (
            patch.object(session, "datetime") as clock,
            patch.object(session.subprocess, "run", return_value=failure) as run,
            patch.object(Path, "read_text", return_value="{}"),
            contextlib.redirect_stdout(output),
        ):
            clock.now.return_value = target + timedelta(seconds=10)
            self.assertFalse(session.run_point(target))
        run.assert_called_once()
        self.assertNotIn("SECRET_REFRESH_TOKEN", output.getvalue())
        self.assertIn("stderr_suppressed=true", output.getvalue())

    def test_expired_slot_does_not_start_scanner(self):
        target = datetime(2026, 11, 2, 17, 30, tzinfo=ZoneInfo("Europe/Amsterdam"))
        with (
            patch.object(session, "datetime") as clock,
            patch.object(session.subprocess, "run") as run,
        ):
            clock.now.return_value = target + timedelta(seconds=241)
            self.assertFalse(session.run_point(target))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
