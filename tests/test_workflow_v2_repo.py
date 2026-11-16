import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
ALLOWED = {"auth-check.yml", "ci.yml", "engineering-quality.yml", "export.yml", "scan.yml"}


class RepoWorkflowContractTests(unittest.TestCase):
    def test_only_v2_workflows_exist(self):
        self.assertEqual({p.name for p in WORKFLOWS.glob("*.yml")}, ALLOWED)

    def test_no_workflow_schedules_itself_the_worker_does(self):
        for path in WORKFLOWS.glob("*.yml"):
            self.assertNotIn("schedule:", path.read_text(encoding="utf-8"), path.name)

    def test_no_workflow_pushes_to_main(self):
        for path in WORKFLOWS.glob("*.yml"):
            self.assertNotIn("HEAD:main", path.read_text(encoding="utf-8"), path.name)

    def test_old_production_layers_are_gone(self):
        for old in ("scanner.py", "scripts", ".recovery", "data"):
            self.assertFalse((ROOT / old).exists(), old)


class QualityGateContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (WORKFLOWS / "engineering-quality.yml").read_text(encoding="utf-8")

    def test_keeps_job_names_and_is_read_only(self):
        for job in ("changes:", "policy:", "ah-tests:", "independent-review:"):
            self.assertIn(job, self.source)
        self.assertIn("contents: read", self.source)

    def test_runs_policy_and_all_test_suites(self):
        self.assertIn("ah_scanner.policy --static-review", self.source)
        self.assertIn("pytest --cov=ah_scanner --cov-fail-under=85", self.source)
        self.assertIn("node --test", self.source)


if __name__ == "__main__":
    unittest.main()
