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


persist = load_module("ah_persist_contract", "scripts/persist.py")
independent = load_module("ah_independent_contract", "scripts/independent_qa.py")


class AHContractTests(unittest.TestCase):
    def test_expected_cadence_contract(self):
        self.assertEqual(len(persist.RAW_SLOTS), 101)
        self.assertEqual(len(persist.SLOTS), 61)
        self.assertEqual(persist.RAW_SLOTS[0], "17:30")
        self.assertEqual(persist.RAW_SLOTS[-1], "22:30")
        self.assertEqual(persist.SLOTS[0], "17:30")
        self.assertEqual(persist.SLOTS[-1], "22:30")

    def test_required_store_scope_matches_independent_verifier(self):
        self.assertEqual(persist.REQUIRED_STORE_IDS, independent.STORE_IDS)

    def test_invalid_auth_never_persists(self):
        observation = {
            "authMode": "anonymous",
            "status": "OK",
            "valid": True,
            "rawDelaySeconds": 10,
            "categories": ["Vlees"],
            "stores": [
                {"storeId": store_id, "fetched": True}
                for store_id in persist.REQUIRED_STORE_IDS
            ],
        }
        self.assertFalse(persist.valid_obs(observation))


if __name__ == "__main__":
    unittest.main()
