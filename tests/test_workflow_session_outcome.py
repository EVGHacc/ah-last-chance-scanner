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

    def test_skipped_gate_is_distinguished_from_failed_gate(self):
        source = (ROOT / ".github/workflows/session.yml").read_text(encoding="utf-8")

        self.assertIn('if [ "\${{ steps.gate.outcome }}" != "success" ]; then', source)
        self.assertIn('if [ "\${{ steps.gate.outputs.run }}" != "true" ]; then', source)
        self.assertIn("exit 1", source)


if __name__ == "__main__":
    unittest.main()
