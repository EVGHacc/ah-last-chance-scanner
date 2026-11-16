import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ExportWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/export.yml").read_text(encoding="utf-8")

    def test_is_manual_only_and_never_scheduled(self):
        self.assertIn("workflow_dispatch:", self.source)
        for forbidden in ("schedule:", "pull_request", "push:"):
            self.assertNotIn(forbidden, self.source)

    def test_writes_only_analysis_to_data_branch_never_main(self):
        self.assertIn("git add analysis", self.source)
        self.assertIn("HEAD:data", self.source)
        self.assertNotIn("HEAD:main", self.source)
        self.assertNotIn("git add -A", self.source)

    def test_has_own_concurrency_group_so_scans_never_wait(self):
        self.assertIn("group: ah-export", self.source)
        self.assertNotIn("group: ah-state", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_needs_no_secrets(self):
        self.assertNotIn("secrets.", self.source)


if __name__ == "__main__":
    unittest.main()
