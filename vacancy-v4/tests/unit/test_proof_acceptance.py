import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.proof_acceptance import validate
def p(f=0):return {"configured_sources":1,"verified_complete":0 if f else 1,"failed":f,"sources":[{"name":"x","unique_jobs":1,"authoritative_total":1,"jobs":[{"job_id":"1","title":"T","summary":"S","job_url":"https://x/j","apply_url":"https://x/a"}]}]}
class T(unittest.TestCase):
 def v(self,x):
  with tempfile.NamedTemporaryFile("w",delete=False) as f:json.dump(x,f);n=f.name
  return validate(n)
 def test_valid(self):self.assertEqual(self.v(p())["failed"],0)
 def test_failed_rejected(self):
  with self.assertRaises(ValueError):self.v(p(1))
 def test_missing_summary_rejected(self):
  x=p();x["sources"][0]["jobs"][0]["summary"]=""
  with self.assertRaises(ValueError):self.v(x)
if __name__=="__main__":unittest.main()
