import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


verify = load_module("production_verify", "scripts/production_verify.py")


class AHProductionVerifierTests(unittest.TestCase):
    def test_partial_but_valid_ah_dataset_fails_production_acceptance(self):
        report = {
            "usable": True,
            "complete": False,
            "quality": "partial",
            "missingRaw": ["17:30"],
            "missingCanonical": ["17:30"],
        }
        with self.assertRaisesRegex(AssertionError, "requires 101/101 raw and 61/61 canonical"):
            verify._ah_result(report)

    def test_complete_ah_dataset_passes_as_complete(self):
        self.assertEqual(
            verify._ah_result({"usable": True, "complete": True, "quality": "complete"}),
            "PASS",
        )

    def test_unusable_ah_dataset_is_rejected(self):
        with self.assertRaises(AssertionError):
            verify._ah_result({"usable": False, "complete": False, "quality": "unusable"})


if __name__ == "__main__":
    unittest.main()
