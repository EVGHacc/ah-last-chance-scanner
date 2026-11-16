import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReportWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/report.yml").read_text(encoding="utf-8")

    def test_is_dispatch_only_and_never_scheduled(self):
        self.assertIn("workflow_dispatch:", self.source)
        for forbidden in ("schedule:", "pull_request", "push:"):
            self.assertNotIn(forbidden, self.source)

    def test_writes_only_reports_to_data_branch_never_main(self):
        self.assertIn("git add reports", self.source)
        self.assertIn("HEAD:data", self.source)
        self.assertNotIn("HEAD:main", self.source)
        self.assertNotIn("git add -A", self.source)

    def test_has_own_concurrency_group_so_scans_never_wait(self):
        self.assertIn("group: ah-report", self.source)
        self.assertNotIn("group: ah-state", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_mail_secrets_only_via_secrets_context_and_no_ah_token(self):
        for name in ("RESEND_API_KEY", "AH_MAIL_FROM", "AH_MAIL_TO"):
            self.assertIn("${{ secrets.%s }}" % name, self.source)
        self.assertNotIn("AH_REFRESH_TOKEN", self.source)  # het rapport raakt AH niet aan


if __name__ == "__main__":
    unittest.main()
