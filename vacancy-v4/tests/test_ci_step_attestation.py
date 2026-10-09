import sys
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.ci_step_attestation import STEP_GROUPS, evaluate_provider_steps, provider_release_gates

RUN_ID=12345
SHA="a"*40

def fixtures():
    run={"id":RUN_ID,"run_attempt":1,"head_sha":SHA,"head_branch":"vacancy-v4-clean-sheet",
         "path":".github/workflows/vacancy-v4-providers.yml","status":"in_progress","conclusion":None}
    steps=[{"name":n,"status":"completed","conclusion":"success"}
           for names in STEP_GROUPS.values() for n in names]
    job={"run_id":RUN_ID,"run_attempt":1,"name":"proof (ashby)",
         "status":"completed","conclusion":"success","steps":steps}
    return run,{"total_count":1,"jobs":[job]}

class StepAttestationTests(unittest.TestCase):
    def check(self, run, jobs):
        return evaluate_provider_steps(run,jobs,"ashby",RUN_ID,1,SHA)
    def test_green_same_run_all_steps(self):
        self.assertTrue(all(self.check(*fixtures()).values()))
    def test_each_required_step_fails_its_gate(self):
        for gate,names in STEP_GROUPS.items():
            with self.subTest(gate=gate):
                r,j=fixtures()
                for step in j["jobs"][0]["steps"]:
                    if step["name"]==names[0]: step["conclusion"]="failure"
                self.assertFalse(self.check(r,j)[gate])
    def test_missing_step_fails_closed(self):
        r,j=fixtures();j["jobs"][0]["steps"].pop()
        self.assertFalse(self.check(r,j)["live_proof"])
    def test_duplicate_step_fails_all(self):
        r,j=fixtures();j["jobs"][0]["steps"].append(j["jobs"][0]["steps"][0])
        self.assertFalse(any(self.check(r,j).values()))
    def test_duplicate_provider_job_fails_all(self):
        r,j=fixtures();j["jobs"].append(dict(j["jobs"][0]));j["total_count"]=2
        self.assertFalse(any(self.check(r,j).values()))
    def test_incomplete_pagination_fails_all(self):
        r,j=fixtures();j["total_count"]=101
        self.assertFalse(any(self.check(r,j).values()))
    def test_wrong_sha_fails_all(self):
        r,j=fixtures();r["head_sha"]="b"*40
        self.assertFalse(any(self.check(r,j).values()))
    def test_wrong_attempt_fails_all(self):
        r,j=fixtures();j["jobs"][0]["run_attempt"]=2
        self.assertFalse(any(self.check(r,j).values()))
    def test_wrong_workflow_fails_all(self):
        r,j=fixtures();r["path"]=".github/workflows/ah.yml"
        self.assertFalse(any(self.check(r,j).values()))
    def test_completed_failed_run_fails_all(self):
        r,j=fixtures();r.update(status="completed",conclusion="failure")
        self.assertFalse(any(self.check(r,j).values()))
    def test_api_error_fails_closed(self):
        with patch("app.ci_step_attestation._run_evidence",side_effect=OSError("timeout")):
            self.assertFalse(any(provider_release_gates("ashby",RUN_ID,1,SHA).values()))
    def test_api_proof_success(self):
        with patch("app.ci_step_attestation._run_evidence",return_value=fixtures()):
            self.assertTrue(all(provider_release_gates("ashby",RUN_ID,1,SHA).values()))
    def test_invalid_identity_does_not_call_api(self):
        with patch("app.ci_step_attestation._run_evidence") as fetch:
            self.assertFalse(any(provider_release_gates("ashby","123",1,SHA).values()))
            fetch.assert_not_called()

if __name__ == "__main__": unittest.main()
