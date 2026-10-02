import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.providers.smartrecruiters import SmartRecruitersError, inventory

def detail(i=1):
    return {"id":str(i),"name":f"Risk Lead {i}","company":{"identifier":"Varrlyn"},"postingUrl":f"https://jobs.smartrecruiters.com/Varrlyn/{i}","applyUrl":f"https://jobs.smartrecruiters.com/Varrlyn/{i}/apply","jobAd":{"sections":{"jobDescription":{"text":"Lead risk and regulatory programmes."},"qualifications":{"text":"Senior leadership experience."}}}}

class SmartRecruitersDeveloperTests(unittest.TestCase):
    def test_paginates_and_reconciles_total(self):
        def fetch(url):
            if "/postings?" in url:
                off=int(url.split("offset=")[1]); ids=[1,2] if off==0 else [3]
                return {"offset":off,"totalFound":3,"content":[{"id":str(i)} for i in ids]}
            return detail(int(url.rsplit("/",1)[1]))
        jobs,total=inventory("Varrlyn",fetch,limit=2)
        self.assertEqual((len(jobs),total),(3,3))
        self.assertTrue(all(j.title and j.summary and j.job_url and j.apply_url for j in jobs))
    def test_duplicate_fails_closed(self):
        with self.assertRaises(SmartRecruitersError): inventory("Varrlyn",lambda u:{"offset":0,"totalFound":2,"content":[{"id":"1"},{"id":"1"}]})
    def test_count_change_fails_closed(self):
        calls=[{"offset":0,"totalFound":2,"content":[{"id":"1"}]},{"offset":1,"totalFound":3,"content":[{"id":"2"}]}]
        with self.assertRaises(SmartRecruitersError): inventory("Varrlyn",lambda u:calls.pop(0),limit=1)
    def test_missing_details_fails_closed(self):
        def fetch(url):
            if "?" in url:return {"offset":0,"totalFound":1,"content":[{"id":"1"}]}
            d=detail();d["jobAd"]={"sections":{}};return d
        with self.assertRaises(SmartRecruitersError): inventory("Varrlyn",fetch)
if __name__=="__main__":unittest.main()
