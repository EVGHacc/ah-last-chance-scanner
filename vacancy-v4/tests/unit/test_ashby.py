import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.providers.ashby import AshbyError, inventory


def job(i, listed=True, description="Own the compliance control framework. Partner with leaders across the business."):
    return {"title":f"Role {i}","jobUrl":f"https://jobs.ashbyhq.com/acme/{i}",
            "applyUrl":f"https://jobs.ashbyhq.com/acme/{i}/application","isListed":listed,
            "location":"Amsterdam","department":"Risk","team":"Compliance",
            "descriptionPlain":description,"publishedAt":"2026-10-02T08:00:00+00:00"}


class AshbyDeveloperTests(unittest.TestCase):
    def test_complete_single_payload_persists_job_metadata(self):
        got=inventory("acme",lambda _:{"apiVersion":"1","jobs":[job("a"),job("b")]})
        self.assertEqual(len(got),2)
        self.assertEqual(got[0].title,"Role a")
        self.assertEqual(got[0].location,"Amsterdam")
        self.assertEqual(got[0].summary,"Own the compliance control framework. Partner with leaders across the business.")
        self.assertEqual(got[0].department,"Risk")
        self.assertEqual(got[0].team,"Compliance")

    def test_summary_falls_back_when_description_missing(self):
        raw=job("a",description="")
        raw.pop("descriptionPlain")
        got=inventory("acme",lambda _:{"apiVersion":"1","jobs":[raw]})
        self.assertIn("Risk",got[0].summary)
        self.assertIn("Amsterdam",got[0].summary)

    def test_unlisted_is_not_public_inventory(self):
        got=inventory("acme",lambda _:{"apiVersion":"1","jobs":[job("a"),job("b",False)]})
        self.assertEqual([x.title for x in got],["Role a"])

    def test_duplicate_fails_closed(self):
        with self.assertRaises(AshbyError):
            inventory("acme",lambda _:{"apiVersion":"1","jobs":[job("a"),job("a")]})

    def test_cross_board_url_fails_closed(self):
        bad=job("a");bad["jobUrl"]="https://jobs.ashbyhq.com/other/a"
        with self.assertRaises(AshbyError): inventory("acme",lambda _:{"apiVersion":"1","jobs":[bad]})

if __name__=="__main__": unittest.main()
