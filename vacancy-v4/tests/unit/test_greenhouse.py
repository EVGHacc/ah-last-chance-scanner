import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.model import Source
from app.providers.greenhouse import GreenhouseError, inventory


SOURCE=Source("employer","Acme","acme.test",("https://acme.test/jobs",),())


def job(i,content="<p>Lead compliance controls. Partner with senior stakeholders.</p>"):
    return {
        "id":i,
        "title":f"Role {i}",
        "location":{"name":"Amsterdam"},
        "absolute_url":f"https://acme.test/jobs/{i}",
        "content":content,
        "departments":[{"name":"Risk"}],
        "offices":[{"name":"Amsterdam Office"}],
        "first_published":"2026-10-01T10:00:00Z",
        "updated_at":"2026-10-02T10:00:00Z",
    }


class GreenhouseDeveloperTests(unittest.TestCase):
    def test_complete_payload_persists_job_metadata(self):
        inv=inventory(SOURCE,"acme",lambda _:{"jobs":[job(1),job(2)],"meta":{"total":2}})
        self.assertEqual(inv.authoritative_total,2)
        self.assertEqual(len(inv.jobs),2)
        self.assertEqual(inv.jobs[0].location,"Amsterdam")
        self.assertEqual(inv.jobs[0].department,"Risk")
        self.assertEqual(inv.jobs[0].office,"Amsterdam Office")
        self.assertIn("Lead compliance controls.",inv.jobs[0].summary)

    def test_count_mismatch_fails_closed(self):
        with self.assertRaises(GreenhouseError):
            inventory(SOURCE,"acme",lambda _:{"jobs":[job(1)],"meta":{"total":2}})

    def test_duplicate_fails_closed(self):
        with self.assertRaises(GreenhouseError):
            inventory(SOURCE,"acme",lambda _:{"jobs":[job(1),job(1)],"meta":{"total":2}})

    def test_cross_domain_job_url_fails_closed(self):
        bad=job(1);bad["absolute_url"]="https://evil.test/jobs/1"
        with self.assertRaises(GreenhouseError):
            inventory(SOURCE,"acme",lambda _:{"jobs":[bad],"meta":{"total":1}})

    def test_same_board_eu_greenhouse_host_is_allowed(self):
        hosted=job(1)
        hosted["absolute_url"]="https://job-boards.eu.greenhouse.io/acme/jobs/1"
        inv=inventory(SOURCE,"acme",lambda _:{"jobs":[hosted],"meta":{"total":1}})
        self.assertEqual(inv.jobs[0].job_url,hosted["absolute_url"])

    def test_cross_board_greenhouse_host_fails_closed(self):
        bad=job(1)
        bad["absolute_url"]="https://job-boards.eu.greenhouse.io/other/jobs/1"
        with self.assertRaises(GreenhouseError):
            inventory(SOURCE,"acme",lambda _:{"jobs":[bad],"meta":{"total":1}})

    def test_missing_content_fails_closed(self):
        bad=job(1);bad.pop("content")
        with self.assertRaises(GreenhouseError):
            inventory(SOURCE,"acme",lambda _:{"jobs":[bad],"meta":{"total":1}})


if __name__=="__main__": unittest.main()
