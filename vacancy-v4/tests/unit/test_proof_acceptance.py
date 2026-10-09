import json
import tempfile
import unittest
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.proof_acceptance import validate

class ProofAcceptanceTests(unittest.TestCase):
    def _write(self,job):
        payload={"configured_sources":1,"failed":0,"verified_complete":1,
                 "sources":[{"name":"OpenAI","coverage":"verified_complete","unique_jobs":1,"jobs":[job]}]}
        f=tempfile.NamedTemporaryFile(mode="w",suffix=".json",delete=False)
        json.dump(payload,f);f.close();return Path(f.name)
    def test_accepts_short_summary_canonical_model(self):
        p=self._write({"job_id":"1","title":"Risk Lead","short_summary":"Own risk",
                       "job_url":"https://example/jobs/1","apply_url":"https://example/jobs/1/apply"})
        self.assertEqual(validate(p)["verified_complete"],1)
    def test_rejects_incomplete_source_list(self):
        p=self._write({"job_id":"1","title":"Risk Lead","short_summary":"Own risk",
                       "job_url":"https://example/jobs/1","apply_url":"https://example/jobs/1/apply"})
        payload=json.loads(p.read_text())
        payload["configured_sources"]=2
        payload["verified_complete"]=2
        p.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,"source count mismatch"):
            validate(p)

    def test_rejects_missing_source_identity(self):
        p=self._write({"job_id":"1","title":"Risk Lead","short_summary":"Own risk",
                       "job_url":"https://example/jobs/1","apply_url":"https://example/jobs/1/apply"})
        payload=json.loads(p.read_text())
        del payload["sources"][0]["name"]
        p.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,"source identity missing"):
            validate(p)

    def test_rejects_missing_summary(self):
        p=self._write({"job_id":"1","title":"Risk Lead",
                       "job_url":"https://example/jobs/1","apply_url":"https://example/jobs/1/apply"})
        with self.assertRaises(ValueError):validate(p)

if __name__=="__main__":unittest.main()
