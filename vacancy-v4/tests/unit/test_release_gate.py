import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.release_gate import REQUIRED_GATES, release_decision


class ReleaseGateTests(unittest.TestCase):
    def test_all_required_gates_must_be_green(self):
        gates = {name: True for name in REQUIRED_GATES}
        self.assertTrue(release_decision(gates)["release_allowed"])

    def test_missing_gate_fails_closed(self):
        gates = {name: True for name in REQUIRED_GATES if name != "independent_qa"}
        decision = release_decision(gates)
        self.assertFalse(decision["release_allowed"])
        self.assertEqual(decision["failed_gates"], ["independent_qa"])

    def test_explicit_false_gate_fails_closed(self):
        gates = {name: True for name in REQUIRED_GATES}
        gates["persistence_safety"] = False
        self.assertFalse(release_decision(gates)["release_allowed"])


if __name__ == "__main__":
    unittest.main()
