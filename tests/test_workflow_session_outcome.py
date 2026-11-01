import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SupervisedSessionWorkflowTests(unittest.TestCase):
    def test_workflow_has_explicit_outcome_gate(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")

        self.assertIn("id: production_tests", source)
        self.assertIn("id: supervised_scan", source)
        self.assertIn("if: always()", source)
        self.assertIn("steps.gate.outcome", source)
        self.assertIn("steps.gate.outputs.run", source)
        self.assertIn("steps.production_tests.outcome", source)
        self.assertIn("steps.supervised_scan.outcome", source)

    def test_session_workflow_cannot_start_from_push_events(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")

        self.assertNotIn("\\n  push:", source)
        self.assertIn("  schedule:", source)
        self.assertIn("  workflow_dispatch:", source)

    def test_failed_gate_and_skipped_scan_are_not_reported_as_success(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")

        self.assertIn("GATE STEP FAILED", source)
        self.assertIn("PRODUCTION TESTS DID NOT SUCCEED", source)
        self.assertIn("SUPERVISED SCAN DID NOT SUCCEED", source)
        self.assertIn("Gate declined this invocation outside the monitoring window", source)
        self.assertIn("exit 1", source)


if __name__ == "__main__":
    unittest.main()
