import json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.proof_acceptance import validate
def example(**overrides):
    job={"job_id":"1","title":"Risk Lead","short_summary":"Own risk","job_url":"https://example.com/1","apply_url":"https://example.com/apply"}
    source={"name":"Example","coverage":"verified_complete","unique_jobs":1,"authoritative_total":1,"exhausted":True,"jobs":[job]}
    source.update(overrides)
    return {"configured_sources":1,"failed":0,"verified_complete":1,"sources":[source]}
class StrictProofAcceptanceTests(unittest.TestCase):
    def check(self,payload,expected=None):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"proof.json";path.write_text(json.dumps(payload))
            if expected:
                with self.assertRaisesRegex(ValueError,expected):validate(path)
            else:self.assertEqual(validate(path),payload)
    def test_positive(self):self.check(example())
    def test_zero_job(self):self.check(example(unique_jobs=0,authoritative_total=0,jobs=[]),"zero or invalid")
    def test_unproven(self):self.check(example(coverage="unproven"),"not independently verified")
    def test_no_coverage(self):self.check(example(coverage=None),"not independently verified")
    def test_pagination(self):self.check(example(exhausted=False),"pagination incomplete")
    def test_boolean_count(self):self.check(example(unique_jobs=True),"zero or invalid")
    def test_bad_https_host(self):
        p=example();p["sources"][0]["jobs"][0]["job_url"]="https://";self.check(p,"job invariant")
    def test_userinfo(self):
        p=example();p["sources"][0]["jobs"][0]["apply_url"]="https://evil@example.com/a";self.check(p,"job invariant")
    def test_total_mismatch(self):self.check(example(authoritative_total=2),"authoritative total mismatch")
if __name__=="__main__":unittest.main()
