import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PrestartWorkflowContractTests(unittest.TestCase):
    def test_production_session_has_dst_aware_1725_schedule(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")
        self.assertIn("- cron: '25 15 * * *'", source)
        self.assertIn("- cron: '25 16 * * *'", source)
        self.assertNotIn("  push:", source)
        self.assertIn("  workflow_dispatch:", source)

    def test_prestart_runs_before_the_supervised_session(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")
        self.assertLess(source.index("id: prestart"), source.index("id: supervised_scan"))
        self.assertIn("python scripts/prestart.py", source)
        self.assertIn("steps.prestart.outcome == 'success'", source)
        self.assertIn("PRESTART CONFIGURATION CHECK DID NOT SUCCEED", source)

    def test_ah_scanner_checks_runs_prestart_regressions(self):
        source = (ROOT / ".github/workflows/probe.yml").read_text(encoding="utf-8")
        self.assertIn("test_ah_prestart.py", source)


if __name__ == "__main__":
    unittest.main()
