import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.providers.eightfold import EightfoldError, inventory

def job(i="1"):
    return {"id":i,"title":"Compliance Lead","description":"Lead regulatory compliance.",
            "jobUrl":f"https://paypal.eightfold.ai/careers/job/{i}",
            "applyUrl":f"https://paypal.eightfold.ai/careers/job/{i}/apply",
            "location":"Amsterdam","department":"Compliance","updatedAt":"2026-10-03T00:00:00Z"}

class EightfoldDeveloperTests(unittest.TestCase):
    def test_inventory_preserves_required_fields(self):
        jobs=inventory("paypal",lambda tenant,cursor,size:{"positions":[job()]})
        self.assertEqual(len(jobs),1); j=jobs[0]
        self.assertTrue(all((j.job_id,j.title,j.short_summary,j.job_url,j.apply_url)))
        self.assertEqual(j.location,"Amsterdam")
    def test_duplicate_fails_closed(self):
        with self.assertRaises(EightfoldError):
            inventory("paypal",lambda t,c,s:{"positions":[job(),job()]})
    def test_missing_required_field_fails_closed(self):
        raw=job();raw.pop("description")
        with self.assertRaises(EightfoldError):
            inventory("paypal",lambda t,c,s:{"positions":[raw]})
    def test_cursor_must_advance(self):
        calls=[{"positions":[job("1")],"nextCursor":"x"},{"positions":[job("2")],"nextCursor":"x"}]
        with self.assertRaises(EightfoldError):
            inventory("paypal",lambda t,c,s:calls.pop(0))
if __name__=="__main__":unittest.main()
