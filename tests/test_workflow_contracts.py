import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_quality_gate_is_read_only_and_has_independent_jobs(self):
        text = self.read(".github/workflows/engineering-quality.yml")
        self.assertIn("permissions:\n  contents: read", text)
        for job in ("policy:", "ah-tests:", "vacancy-tests:", "independent-review:"):
            self.assertIn(job, text)
        self.assertIn("changes:", text)
        self.assertIn("needs: [changes, policy, ah-tests, vacancy-tests]", text)
        self.assertIn("if: needs.changes.outputs.ah == 'true'", text)
        self.assertIn("if: needs.changes.outputs.vacancy == 'true'", text)
        self.assertNotIn("contents: write", text)

    def test_production_verifier_is_read_only_and_post_run(self):
        text = self.read(".github/workflows/production-verifier.yml")
        self.assertIn("workflow_run:", text)
        self.assertIn("'AH supervised evening session'", text)
        self.assertIn("'Vacancy Monitor 106'", text)
        self.assertIn("python scripts/production_verify.py --project ah", text)
        self.assertIn("python scripts/production_verify.py --project vacancy", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("secrets.", text)

    def test_quality_gate_enforces_project_regression_suites(self):
        text = self.read(".github/workflows/engineering-quality.yml")
        self.assertIn("scripts/independent_qa.py --self-test", text)
        self.assertIn("scripts/selftest.py", text)
        self.assertIn("unittest discover -s vacancy-monitor -p 'test_*.py'", text)
        self.assertIn("engineering_gate.py --base", text)


if __name__ == "__main__":
    unittest.main()
