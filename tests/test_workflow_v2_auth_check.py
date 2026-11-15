import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AuthCheckWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/auth-check.yml").read_text(encoding="utf-8")

    def test_is_manual_only_and_never_scheduled(self):
        self.assertIn("workflow_dispatch:", self.source)
        self.assertNotIn("schedule:", self.source)
        self.assertNotIn("pull_request", self.source)
        self.assertNotIn("push:", self.source)

    def test_rotated_state_goes_to_data_branch_never_main(self):
        self.assertIn("git push origin HEAD:data", self.source)
        self.assertNotIn("HEAD:main", self.source)

    def test_state_writes_are_serialized_and_never_cancelled(self):
        self.assertIn("group: ah-state", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_secret_only_via_secrets_context_and_not_echoed(self):
        self.assertIn("${{ secrets.AH_REFRESH_TOKEN }}", self.source)
        self.assertNotIn("echo $AH_REFRESH_TOKEN", self.source)
        self.assertNotIn("echo \"$AH_REFRESH_TOKEN\"", self.source)


class CiWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    def test_ci_is_read_only_and_runs_lint_format_and_tests(self):
        self.assertIn("contents: read", self.source)
        self.assertIn("ruff check", self.source)
        self.assertIn("ruff format --check", self.source)
        self.assertIn("pytest --cov=ah_scanner --cov-fail-under=85", self.source)

    def test_ci_runs_worker_tests(self):
        self.assertIn("node --test", self.source)
        self.assertIn("working-directory: worker", self.source)


if __name__ == "__main__":
    unittest.main()
