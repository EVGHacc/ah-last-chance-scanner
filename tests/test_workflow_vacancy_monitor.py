import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VacancyMonitorWorkflowContractTests(unittest.TestCase):
    def test_half_hourly_schedule_preserves_every_cycle(self):
        text = (ROOT / ".github/workflows/vacancy-monitor.yml").read_text(encoding="utf-8")
        self.assertIn('cron: "7,37 * * * *"', text)
        self.assertIn('timezone: "Europe/Amsterdam"', text)
        self.assertIn("group: vacancy-monitor-106-half-hourly", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("queue: max", text)
        self.assertNotIn('cron: "30 5 * * 1-5"', text)


if __name__ == "__main__":
    unittest.main()
