"""Workflow-level contracts for the AH production control plane."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AHSchedulerWorkflowContractTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_only_session_workflow_owns_production_schedule(self):
        session = self.read(".github/workflows/session.yml")
        guardian = self.read(".github/workflows/guardian.yml")
        fallback = self.read(".github/workflows/fallback-qa.yml")
        self.assertIn("  schedule:", session)
        self.assertIn("group: ah-production-single-writer", session)
        self.assertIn("cancel-in-progress: false", session)
        self.assertNotIn("  schedule:", guardian)
        self.assertNotIn("workflow_dispatch:", guardian)
        self.assertIn("  schedule:", fallback)
        self.assertNotIn("workflow_dispatch:", fallback)

    def test_watchdog_and_guardian_are_read_only(self):
        guardian = self.read(".github/workflows/guardian.yml")
        fallback = self.read(".github/workflows/fallback-qa.yml")
        watchdog = self.read("scripts/session_watchdog.py")
        self.assertIn("contents: read", guardian)
        self.assertIn("contents: read", fallback)
        self.assertIn("actions: read", fallback)
        self.assertNotIn("contents: write", guardian + fallback)
        self.assertNotIn("actions: write", guardian + fallback)
        self.assertNotIn("/cancel", watchdog)
        self.assertNotIn("/dispatches", watchdog)
        self.assertNotIn('method="POST"', watchdog)

    def test_no_production_workflow_cancels_running_work(self):
        for path in (
            ".github/workflows/session.yml",
            ".github/workflows/guardian.yml",
            ".github/workflows/fallback-qa.yml",
        ):
            with self.subTest(path=path):
                self.assertNotIn("cancel-in-progress: true", self.read(path))

    def test_fallback_qa_runs_watchdog_regression_suite(self):
        fallback = self.read(".github/workflows/fallback-qa.yml")
        self.assertIn("python -m unittest discover -s tests -p 'test_ah_scheduler_watchdog.py' -v", fallback)
        self.assertIn("actions: read", fallback)
        self.assertNotIn("actions: write", fallback)


if __name__ == "__main__":
    unittest.main()
