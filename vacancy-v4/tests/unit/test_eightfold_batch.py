import sys
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.eightfold_batch import run_batch

class EightfoldBatchTests(unittest.TestCase):
    def test_unproven_public_endpoint_fails_closed(self):
        r=run_batch(lambda url: {"positions":[]})
        self.assertEqual((r["verified_complete"],r["failed"]),(0,1))
        self.assertIn("BLOCKED",r["sources"][0]["error"])

if __name__=="__main__":unittest.main()
