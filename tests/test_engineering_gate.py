import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gate = load_module("engineering_gate", "scripts/engineering_gate.py")


class ChangePolicyTests(unittest.TestCase):
    def test_ah_code_requires_dedicated_test(self):
        errors = gate.evaluate_changes(["scanner.py"])
        self.assertTrue(any("AH production" in error for error in errors))

    def test_ah_code_with_test_passes(self):
        self.assertEqual(
            gate.evaluate_changes(["scanner.py", "tests/test_ah_scanner.py"]),
            [],
        )

    def test_vacancy_code_requires_test(self):
        errors = gate.evaluate_changes(["vacancy-monitor/scanner.py"])
        self.assertTrue(any("Vacancy production" in error for error in errors))

    def test_vacancy_code_with_test_passes(self):
        self.assertEqual(
            gate.evaluate_changes(
                ["vacancy-monitor/scanner.py", "vacancy-monitor/test_scanner.py"]
            ),
            [],
        )

    def test_workflow_requires_workflow_contract_test(self):
        errors = gate.evaluate_changes([".github/workflows/session.yml"])
        self.assertTrue(any("workflow changed" in error for error in errors))

    def test_source_and_generated_evidence_cannot_be_mixed(self):
        errors = gate.evaluate_changes(
            ["scanner.py", "tests/test_ah_scanner.py", "data/status.json"]
        )
        self.assertTrue(any("generated production snapshots" in error for error in errors))

    def test_data_only_bot_commit_is_allowed(self):
        self.assertEqual(
            gate.evaluate_changes(["data/status.json", "data/2026-10-01.jsonl"]),
            [],
        )

    def test_engineering_control_plane_requires_engineering_test(self):
        errors = gate.evaluate_changes(["scripts/production_verify.py"])
        self.assertTrue(any("control-plane" in error for error in errors))

    def test_static_review_reports_missing_control_plane(self):
        with tempfile.TemporaryDirectory() as tmp:
            errors = gate.static_review(Path(tmp))
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
