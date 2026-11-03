import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PrestartWorkflowContractTests(unittest.TestCase):
    def test_production_session_has_primary_and_backup_dst_aware_schedules(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")
        for cron in ("25 15", "25 16", "28 15", "28 16"):
            self.assertIn(f"- cron: '{cron} * * *'", source)
        self.assertNotIn("  push:", source)
        self.assertIn("  workflow_dispatch:", source)
        self.assertIn("recovery_confirmation:", source)
        self.assertIn("Consume one-time recovery authorization", source)
        self.assertIn("git push origin HEAD:main", source)
        self.assertLess(source.index("Consume one-time recovery authorization"), source.index("id: supervised_scan"))
        self.assertIn("group: ah-production-single-writer", source)
        self.assertIn("cancel-in-progress: false", source)

    def test_prestart_runs_before_the_supervised_session(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")
        self.assertLess(source.index("id: prestart"), source.index("id: supervised_scan"))
        self.assertIn("python scripts/prestart.py", source)
        self.assertIn("steps.prestart.outcome == 'success'", source)
        self.assertIn("PRESTART CONFIGURATION CHECK DID NOT SUCCEED", source)
        self.assertIn("python -m unittest discover -s tests -p 'test_ah_prestart.py' -v", source)

    def test_ah_scanner_checks_run_prestart_regressions_on_pull_requests(self):
        source = (ROOT / ".github/workflows/probe.yml").read_text(encoding="utf-8")
        self.assertIn("  pull_request:", source)
        self.assertIn("test_ah_prestart.py", source)


if __name__ == "__main__":
    unittest.main()
