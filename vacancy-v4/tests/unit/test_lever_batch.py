import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.lever_batch import run_batch

class LeverBatchTests(unittest.TestCase):
    def test_green_inventory_is_persistable(self):
        def fetch(url):
            return [{"id":"1","text":"Risk Lead","descriptionPlain":"Own risk.",
                     "hostedUrl":"https://jobs.eu.lever.co/pnlfin/1",
                     "applyUrl":"https://jobs.eu.lever.co/pnlfin/1/apply",
                     "categories":{"location":"Amsterdam"}}]
        r=run_batch(fetch)
        self.assertEqual((r["verified_complete"],r["failed"]),(1,0))
        self.assertEqual(len(r["sources"][0]["jobs"]),1)
    def test_failure_is_non_authoritative(self):
        r=run_batch(lambda url: (_ for _ in ()).throw(RuntimeError("network")))
        self.assertEqual((r["verified_complete"],r["failed"]),(0,1))
        self.assertEqual(r["sources"][0]["jobs"],[])
if __name__=="__main__":unittest.main()
