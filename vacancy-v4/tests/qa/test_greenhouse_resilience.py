import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.greenhouse_batch import run_batch
from app.transport import TransportError


DOMAINS={"stripe":"stripe.com","ripple":"ripple.com","remotecom":"remote.com"}


def good(board):
    domain=DOMAINS[board]
    return {"jobs":[{
        "id":1,
        "title":"Compliance Lead",
        "location":{"name":"Amsterdam"},
        "absolute_url":f"https://{domain}/jobs/1",
        "content":"Lead compliance governance and controls. Advise senior stakeholders.",
        "departments":[{"name":"Compliance"}],
        "offices":[{"name":"Amsterdam"}],
        "updated_at":"2026-10-02T08:00:00Z",
    }],"meta":{"total":1}}


class GreenhouseIndependentQA(unittest.TestCase):
    def test_network_failure_isolated_per_source(self):
        def fetch(url):
            board=url.split("/boards/")[1].split("/")[0]
            if board=="stripe": raise TransportError("network failure")
            return good(board)
        result=run_batch(fetch)
        self.assertEqual(result["verified_complete"],2)
        failed=next(x for x in result["sources"] if x["name"]=="Stripe")
        self.assertEqual(failed["coverage"],"unproven")
        self.assertEqual(failed["jobs"],[])

    def test_rate_limit_is_never_empty_success(self):
        def fetch(url):
            board=url.split("/boards/")[1].split("/")[0]
            if board=="ripple": raise TransportError("HTTP 429")
            return good(board)
        result=run_batch(fetch)
        row=next(x for x in result["sources"] if x["name"]=="Ripple")
        self.assertEqual(row["coverage"],"unproven")
        self.assertFalse(row["exhausted"])

    def test_schema_change_is_unproven(self):
        def fetch(url):
            board=url.split("/boards/")[1].split("/")[0]
            return {"postings":[],"total":0} if board=="remotecom" else good(board)
        result=run_batch(fetch)
        row=next(x for x in result["sources"] if x["name"]=="Remote.com")
        self.assertEqual(row["coverage"],"unproven")
        self.assertIn("GreenhouseError",row["error"])

    def test_count_mismatch_is_unproven(self):
        def fetch(url):
            board=url.split("/boards/")[1].split("/")[0]
            p=good(board)
            if board=="stripe": p["meta"]["total"]=2
            return p
        result=run_batch(fetch)
        row=next(x for x in result["sources"] if x["name"]=="Stripe")
        self.assertEqual(row["coverage"],"unproven")
        self.assertIn("count mismatch",row["error"])

    def test_duplicate_is_unproven(self):
        def fetch(url):
            board=url.split("/boards/")[1].split("/")[0]
            p=good(board)
            if board=="ripple":
                p["jobs"]=[p["jobs"][0],dict(p["jobs"][0])]
                p["meta"]["total"]=2
            return p
        result=run_batch(fetch)
        row=next(x for x in result["sources"] if x["name"]=="Ripple")
        self.assertEqual(row["coverage"],"unproven")
        self.assertIn("duplicate",row["error"])

    def test_missing_summary_data_is_unproven(self):
        def fetch(url):
            board=url.split("/boards/")[1].split("/")[0]
            p=good(board)
            if board=="remotecom": p["jobs"][0]["content"]=""
            return p
        result=run_batch(fetch)
        row=next(x for x in result["sources"] if x["name"]=="Remote.com")
        self.assertEqual(row["coverage"],"unproven")
        self.assertEqual(row["jobs"],[])


if __name__=="__main__": unittest.main()
