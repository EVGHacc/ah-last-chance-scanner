import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_quality_gate_is_read_only_and_has_independent_jobs(self):
        text = self.read(".github/workflows/engineering-quality.yml")
        self.assertIn("permissions:\n  contents: read", text)
            self.assertIn(job, text)
        self.assertIn("changes:", text)
        self.assertIn("needs: [changes, policy, ah-tests]", text)
        self.assertIn("if: needs.changes.outputs.ah == 'true'", text)
        self.assertNotIn("contents: write", text)

    def test_production_verifier_is_read_only_and_post_run(self):
        text = self.read(".github/workflows/production-verifier.yml")
        self.assertIn("workflow_run:", text)
        self.assertIn("'AH supervised evening session'", text)
        self.assertIn("python scripts/production_verify.py", text)
        self.assertNotIn("continue-on-error: true", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("secrets.", text)

    def test_ah_production_verifier_requires_complete_dataset(self):
        verifier = self.read("scripts/production_verify.py")
        self.assertIn("require_complete=True", verifier)
        self.assertIn("101/101 raw and 61/61 canonical", verifier)
        qa = self.read("scripts/independent_qa.py")
        self.assertIn('item.get("categories") == ["Vlees"]', qa)
        self.assertIn("and bad == 0", qa)

    def test_automatic_recovery_entrypoints_are_removed(self):
        self.assertFalse((ROOT / ".github/workflows/external-recovery.yml").exists())
        self.assertFalse((ROOT / ".github/workflows/external-recovery-tests.yml").exists())
        self.assertFalse((ROOT / "scripts/external_start_recovery.py").exists())
        session = self.read(".github/workflows/session.yml")
        self.assertNotIn("workflow_dispatch:", session)
        self.assertNotIn("Consume one-time recovery authorization", session)

    def test_quality_gate_enforces_project_regression_suites(self):
        text = self.read(".github/workflows/engineering-quality.yml")
        self.assertIn("scripts/independent_qa.py --self-test", text)
        self.assertIn("scripts/selftest.py", text)
        self.assertIn("engineering_gate.py --base", text)


if __name__ == "__main__":
    unittest.main()
