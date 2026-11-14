import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PrestartWorkflowContractTests(unittest.TestCase):
    def test_production_session_has_one_dst_aware_prestart(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")
        for cron in ("25 15", "25 16", "28 15", "28 16"):
            self.assertIn(f"- cron: '{cron} * * *'", source)
        self.assertNotIn("  push:", source)
        self.assertNotIn("  workflow_dispatch:", source)
        self.assertNotIn("recovery_confirmation:", source)
        self.assertNotIn("git push origin HEAD:main", source)
        self.assertIn("GATE_DECISION", source)
        self.assertIn("Claim today's production session", source)
        self.assertIn("steps.claim.outcome == 'success'", source)
        self.assertIn("already claimed", source)
        self.assertIn("EXPECTED PRESTART MISSED OR INVALID", source)
        self.assertIn("group: ah-production-single-writer", source)
        self.assertIn("cancel-in-progress: false", source)

    def test_prestart_runs_before_the_supervised_session(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")
        self.assertLess(source.index("id: prestart"), source.index("id: supervised_scan"))
        self.assertIn("python scripts/prestart.py", source)
        self.assertIn("python scripts/production_health.py --preflight", source)
        self.assertIn("steps.prestart.outcome == 'success'", source)
        self.assertIn("PRESTART CONFIGURATION CHECK DID NOT SUCCEED", source)
        self.assertIn("python -m unittest discover -s tests -p 'test_ah_prestart.py' -v", source)

    def test_ah_scanner_checks_run_prestart_regressions_on_pull_requests(self):
        source = (ROOT / ".github/workflows/probe.yml").read_text(encoding="utf-8")
        self.assertIn("  pull_request:", source)
        self.assertIn("test_ah_prestart.py", source)


if __name__ == "__main__":
    unittest.main()
