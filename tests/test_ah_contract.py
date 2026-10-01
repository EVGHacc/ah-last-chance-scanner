import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
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

    def _write_partial_day(self, root):
        day = "2026-10-01"
        slot = "18:00"
        at = datetime.fromisoformat(f"{day}T{slot}:00+02:00")
        row = {
            "date": day,
            "rawScheduledSlot": slot,
            "scheduledSlot": slot,
            "rawScheduledAt": at.isoformat(),
            "scheduledAt": at.isoformat(),
            "startedAt": (at + timedelta(seconds=10)).isoformat(),
            "checkedAt": (at + timedelta(seconds=15)).isoformat(),
            "rawDelaySeconds": 10,
            "delaySeconds": 10,
            "valid": True,
            "status": "OK",
            "authMode": "user-refresh",
            "categories": ["Vlees", "Bakkerij"],
            "stores": [
                {"storeId": store_id, "fetched": True}
                for store_id in independent.STORE_IDS
            ],
        }
        (root / f"{day}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        (root / "status.json").write_text(
            json.dumps(
                {
                    "date": day,
                    "authMode": "user-refresh",
                    "category": "Vlees",
                    "rawExpected": 101,
                    "canonicalExpected": 61,
                    "stores": sorted(independent.STORE_IDS),
                    "rawSeen": [slot],
                    "canonicalSeen": [slot],
                    "rawMissing": [s for s in independent.RAW if s != slot],
                    "canonicalMissing": [s for s in independent.CANONICAL if s != slot],
                }
            ),
            encoding="utf-8",
        )
        return datetime.fromisoformat(day + "T22:35:00+02:00")

    def test_partial_valid_day_remains_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = self._write_partial_day(root)
            report = independent.verify(root, now, require_complete=False)
        self.assertTrue(report["usable"])
        self.assertFalse(report["complete"])
        self.assertEqual(report["quality"], "partial")
        self.assertGreater(len(report["missingRaw"]), 0)
        self.assertGreater(len(report["missingCanonical"]), 0)

    def test_strict_completeness_mode_still_rejects_missing_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = self._write_partial_day(root)
            with self.assertRaises(AssertionError):
                independent.verify(root, now, require_complete=True)


if __name__ == "__main__":
    unittest.main()
