import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RawHistoryRepairWorkflowTests(unittest.TestCase):
    def test_historical_repair_requires_explicit_manual_dispatch(self):
        source = (ROOT / ".github/workflows/raw-history-repair.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("\n  push:", source)
        self.assertIn("python scripts/backfill_raw_history.py --date 2026-10-06", source)
        self.assertIn("python scripts/backfill_raw_history.py --date 2026-10-06 --verify-only", source)
        self.assertIn("git add data/raw/2026-10-06", source)


if __name__ == "__main__":
    unittest.main()
