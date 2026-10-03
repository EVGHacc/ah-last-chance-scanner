import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.providers.lever import LeverError, inventory


def _job(job_id="1"):
    return {
        "id": job_id,
        "text": "Risk Lead",
        "descriptionPlain": "Own the enterprise risk programme.",
        "hostedUrl": f"https://jobs.eu.lever.co/pnlfin/{job_id}",
        "applyUrl": f"https://jobs.eu.lever.co/pnlfin/{job_id}/apply",
        "categories": {
            "location": "Amsterdam",
            "department": "Risk",
            "team": "Compliance",
            "office": "Amsterdam",
        },
        "createdAt": 1,
        "updatedAt": 2,
    }


class LeverDeveloperTests(unittest.TestCase):
    def test_inventory_preserves_hard_job_data_invariant(self):
        jobs = inventory("pnlfin", lambda site, offset, limit: [_job()])
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job.job_id, "1")
        self.assertEqual(job.title, "Risk Lead")
        self.assertTrue(job.short_summary)
        self.assertTrue(job.job_url.endswith("/1"))
        self.assertTrue(job.apply_url.endswith("/1/apply"))
        self.assertEqual(job.location, "Amsterdam")
        self.assertEqual(job.department, "Risk")
        self.assertEqual(job.team, "Compliance")
        self.assertEqual(job.office, "Amsterdam")
        self.assertEqual(job.created_at, 1)
        self.assertEqual(job.updated_at, 2)

    def test_inventory_fails_closed_when_required_field_missing(self):
        for field in ["id", "text", "descriptionPlain", "hostedUrl", "applyUrl"]:
            with self.subTest(field=field):
                raw = _job()
                raw.pop(field)
                with self.assertRaisesRegex(LeverError, "required posting fields missing"):
                    inventory("pnlfin", lambda site, offset, limit, raw=raw: [raw])

    def test_inventory_rejects_duplicate_ids_across_pages(self):
        def fetch(site, offset, limit):
            return [_job(str(i)) for i in range(100)] if offset == 0 else [_job("0")]
        with self.assertRaisesRegex(LeverError, "duplicate/page-wrap"):
            inventory("pnlfin", fetch)

    def test_inventory_rejects_non_array_payload(self):
        with self.assertRaisesRegex(LeverError, "expected JSON array"):
            inventory("pnlfin", lambda site, offset, limit: {"jobs": []})


if __name__ == "__main__":
    unittest.main()
