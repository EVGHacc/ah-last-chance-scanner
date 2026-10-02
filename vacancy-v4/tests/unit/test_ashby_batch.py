import json
import sys
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.ashby_batch import load_config, run_batch


def payload(board, count=2):
    return {"apiVersion":"1","jobs":[
        {"title":f"Role {i}",
         "jobUrl":f"https://jobs.ashbyhq.com/{board}/{i}",
         "applyUrl":f"https://jobs.ashbyhq.com/{board}/{i}/application",
         "isListed":True}
        for i in range(count)
    ]}


class AshbyBatchDeveloperTests(unittest.TestCase):
    def test_configured_sources_are_real_v4_targets(self):
        result=run_batch(lambda url: payload(url.rsplit("/",1)[-1],1))
        self.assertEqual(result["configured_sources"],4)
        self.assertEqual(result["verified_complete"],4)
        self.assertEqual(result["failed"],0)

    def test_hash_is_stable_for_complete_inventory(self):
        first=run_batch(lambda url: payload(url.rsplit("/",1)[-1],2))
        second=run_batch(lambda url: payload(url.rsplit("/",1)[-1],2))
        self.assertEqual(
            [x["jobs_sha256"] for x in first["sources"]],
            [x["jobs_sha256"] for x in second["sources"]],
        )

    def test_duplicate_config_source_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"c.json"
            p.write_text(json.dumps({"schema_version":1,"provider":"ashby","sources":[
                {"name":"OpenAI","board":"openai","first_party_evidence_url":"https://openai.com/careers/search/"},
                {"name":"OpenAI","board":"openai","first_party_evidence_url":"https://openai.com/careers/search/"}
            ]}))
            with self.assertRaises(ValueError): load_config(p)


if __name__=="__main__": unittest.main()
