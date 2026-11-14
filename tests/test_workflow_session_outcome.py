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
        self.assertIn("GATE_DECISION", source)
        self.assertIn("steps.production_tests.outcome", source)
        self.assertIn("steps.supervised_scan.outcome", source)

    def test_session_workflow_cannot_start_from_push_events(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")

        self.assertNotIn("  push:", source)
        self.assertIn("  schedule:", source)
        self.assertNotIn("  workflow_dispatch:", source)

    def test_failed_gate_and_skipped_scan_are_not_reported_as_success(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")

        self.assertIn("SCHEDULE GATE FAILED", source)
        self.assertIn("EXPECTED PRESTART MISSED OR INVALID", source)
        self.assertIn("PRODUCTION TESTS DID NOT SUCCEED", source)
        self.assertIn("SUPERVISED SCAN DID NOT SUCCEED", source)
        self.assertIn("DST alternate schedule is intentionally inactive today", source)
        self.assertIn("exit 1", source)


if __name__ == "__main__":
    unittest.main()
