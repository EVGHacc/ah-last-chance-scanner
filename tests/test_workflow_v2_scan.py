import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ScanWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/scan.yml").read_text(encoding="utf-8")

    def test_only_workflow_dispatch_with_required_scheduled_at(self):
        self.assertIn("workflow_dispatch:", self.source)
        self.assertIn("scheduled_at:", self.source)
        self.assertIn("required: true", self.source)
        for forbidden in ("schedule:", "pull_request", "push:"):
            self.assertNotIn(forbidden, self.source)

    def test_serialized_with_auth_state_and_never_cancelled(self):
        self.assertIn("group: ah-state", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_writes_only_to_data_branch(self):
        self.assertIn("HEAD:data", self.source)
        self.assertNotIn("HEAD:main", self.source)

    def test_data_is_persisted_even_when_scan_fails(self):
        persist = self.source.split("Persist data", 1)[1]
        self.assertIn("if: always()", persist.split("run:", 1)[0])

    def test_secret_only_via_secrets_context(self):
        self.assertIn("${{ secrets.AH_REFRESH_TOKEN }}", self.source)
        self.assertNotIn("echo $AH_REFRESH_TOKEN", self.source)


if __name__ == "__main__":
    unittest.main()
