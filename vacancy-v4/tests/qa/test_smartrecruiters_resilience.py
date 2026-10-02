import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.providers.smartrecruiters import SmartRecruitersError, inventory
from app.smartrecruiters_batch import run_batch
from app.transport import TransportError

def listing(ids,total=None,offset=0):
    return {"content":[{"id":x} for x in ids],"totalFound":len(ids) if total is None else total,"offset":offset}
def detail(i):
    return {"id":i,"name":"Compliance Lead","company":{"identifier":"Varrlyn"},
            "postingUrl":f"https://jobs.smartrecruiters.com/Varrlyn/{i}",
            "applyUrl":f"https://jobs.smartrecruiters.com/Varrlyn/{i}/apply",
            "jobAd":{"sections":{"jobDescription":{"text":"Lead regulatory compliance and governance."}}}}

class SmartRecruitersIndependentQA(unittest.TestCase):
    def test_network_failure_is_fail_closed(self):
        r=run_batch(lambda url: (_ for _ in ()).throw(TransportError("network failure")))
        self.assertEqual((r["verified_complete"],r["failed"]),(0,1));self.assertEqual(r["sources"][0]["jobs"],[])
    def test_http_429_is_fail_closed(self):
        r=run_batch(lambda url: (_ for _ in ()).throw(TransportError("HTTP 429")))
        self.assertEqual(r["sources"][0]["coverage"],"unproven")
    def test_malformed_payload_is_not_coverage(self):
        r=run_batch(lambda url:{"unexpected":[]});self.assertEqual(r["sources"][0]["coverage"],"unproven")
    def test_duplicate_is_rejected(self):
        with self.assertRaises(SmartRecruitersError):inventory("Varrlyn",lambda url:listing(["x","x"],2))
    def test_incomplete_pagination_is_rejected(self):
        with self.assertRaises(SmartRecruitersError):inventory("Varrlyn",lambda url:{"content":[],"totalFound":2,"offset":0})
    def test_detail_company_mismatch_is_rejected(self):
        def fetch(url):
            if "/postings?" in url:return listing(["x"],1)
            d=detail("x");d["company"]["identifier"]="Other";return d
        with self.assertRaises(SmartRecruitersError):inventory("Varrlyn",fetch)
    def test_missing_summary_is_rejected(self):
        def fetch(url):
            if "/postings?" in url:return listing(["x"],1)
            d=detail("x");d["jobAd"]["sections"]={};return d
        with self.assertRaises(SmartRecruitersError):inventory("Varrlyn",fetch)
if __name__=="__main__":unittest.main()
