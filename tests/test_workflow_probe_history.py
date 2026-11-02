import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AHProbeWorkflowTests(unittest.TestCase):
    def test_scanner_checks_do_not_depend_on_historical_archive(self):
        workflow = (ROOT / ".github/workflows/probe.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/selftest.py", workflow)
        self.assertIn("python scripts/independent_qa.py --self-test", workflow)
        self.assertNotIn("central_data_check.py", workflow)
        self.assertNotIn("daily_counts.csv", workflow)


if __name__ == "__main__":
    unittest.main()
