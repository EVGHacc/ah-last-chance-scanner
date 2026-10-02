import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.coverage_ledger import build
class T(unittest.TestCase):
 def test_only_valid_accepted_counts(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,"ashby-proof.json").write_text(json.dumps({"provider":"x","sources":[{"name":"good","coverage":"verified_complete","unique_jobs":1,"jobs":[{"job_id":"1"}]},{"name":"bad","coverage":"unproven","unique_jobs":0,"jobs":[]}]}))
   r=build(d);self.assertEqual(r["accepted_coverage"],1);self.assertEqual(len(r["attempted"]),2)
 def test_empty_never_counts(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,"ashby-proof.json").write_text("");self.assertEqual(build(d)["accepted_coverage"],0)
if __name__=="__main__":unittest.main()
