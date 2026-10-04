import json
import sys
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.eightfold_batch import run_batch

class EightfoldBatchTests(unittest.TestCase):
    def test_unproven_public_endpoint_fails_closed(self):
        config={"schema_version":1,"provider":"eightfold","sources":[{"name":"PayPal","tenant":"paypal"}]}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"eightfold_sources.json"
            path.write_text(json.dumps(config),encoding="utf-8")
            r=run_batch(lambda url: {"positions":[]},config_path=path)
        self.assertEqual((r["verified_complete"],r["failed"]),(0,1))
        self.assertIn("BLOCKED",r["sources"][0]["error"])

if __name__=="__main__":unittest.main()
