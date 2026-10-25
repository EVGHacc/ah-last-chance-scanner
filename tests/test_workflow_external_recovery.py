"""Verify the external AH watchdog's least-privilege dispatch workflow."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExternalRecoveryWorkflowContract(unittest.TestCase):
    def test_external_entrypoint_is_dispatch_only(self):
        source = (ROOT / ".github/workflows/external-recovery.yml").read_text()
        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("schedule:", source)
        self.assertIn("contents: read", source)
        self.assertIn("actions: write", source)
        self.assertIn("scripts/external_start_recovery.py --self-test", source)
        self.assertIn("python scripts/external_start_recovery.py", source)

    def test_pr_validation_has_no_write_permission(self):
        source = (ROOT / ".github/workflows/external-recovery-tests.yml").read_text()
        self.assertIn("pull_request:", source)
        self.assertIn("contents: read", source)
        self.assertNotIn("actions: write", source)


if __name__ == "__main__":
    unittest.main()
