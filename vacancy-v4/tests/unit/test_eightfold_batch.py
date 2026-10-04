import json
import sys
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.eightfold_batch import run_batch

class EightfoldBatchTests(unittest.TestCase):
    def _config(self):
        return {"schema_version":1,"provider":"eightfold","sources":[{
            "name":"PayPal","tenant":"paypal","domain":"paypal.com",
            "careers_url":"https://paypal.eightfold.ai/careers",
            "pcsx_search_endpoint":"https://paypal.eightfold.ai/api/pcsx/search",
            "pcsx_details_endpoint":"https://paypal.eightfold.ai/api/pcsx/position_details"}]}

    def test_missing_pcsx_contract_fails_closed(self):
        config={"schema_version":1,"provider":"eightfold","sources":[{"name":"PayPal","tenant":"paypal"}]}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"eightfold_sources.json"; path.write_text(json.dumps(config),encoding="utf-8")
            r=run_batch(lambda url: {},config_path=path)
        self.assertEqual((r["verified_complete"],r["failed"]),(0,1))
        self.assertIn("BLOCKED",r["sources"][0]["error"])

    def test_pcsx_reconciles_count_and_enriches_description(self):
        def fetch(url):
            if "position_details" in url:
                return {"data":{"jobDescription":"Full role description"}}
            return {"data":{"count":1,"positions":[{"id":123,"name":"Risk Lead","positionUrl":"/careers/job/123-risk-lead?domain=paypal.com","locations":["Amsterdam"],"department":"Risk","postedTs":99}]}}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"eightfold_sources.json"; path.write_text(json.dumps(self._config()),encoding="utf-8")
            r=run_batch(fetch,config_path=path)
        self.assertEqual((r["verified_complete"],r["failed"]),(1,0))
        job=r["sources"][0]["jobs"][0]
        self.assertEqual(job["job_id"],"123")
        self.assertEqual(job["short_summary"],"Full role description")
        self.assertEqual(job["job_url"],job["apply_url"])

    def test_pcsx_fails_closed_on_short_inventory(self):
        def fetch(url):
            if "position_details" in url:
                return {"data":{"jobDescription":"Description"}}
            return {"data":{"count":11,"positions":[{"id":1,"name":"Role","positionUrl":"/careers/job/1"}]}}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"eightfold_sources.json"; path.write_text(json.dumps(self._config()),encoding="utf-8")
            r=run_batch(fetch,config_path=path)
        self.assertEqual((r["verified_complete"],r["failed"]),(0,1))
        self.assertIn("pagination ended",r["sources"][0]["error"])

if __name__=="__main__":unittest.main()
