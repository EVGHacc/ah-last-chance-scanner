import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.ashby_batch import run_batch
from app.transport import TransportError


ID="00000000-0000-4000-8000-000000000001"

def good(board):
    return {"apiVersion":"1","jobs":[{
        "title":"Role",
        "jobUrl":f"https://jobs.ashbyhq.com/{board}/{ID}",
        "applyUrl":f"https://jobs.ashbyhq.com/{board}/{ID}/application",
        "isListed":True,
    }]}

def matching_html(url):
    if "jobs.mollie.com/vacancies/" in url:
        job_id=url.rstrip("/").split("/")[-1]
        return (
            f'<a href="https://jobs.ashbyhq.com/mollie/{job_id}">job</a>'
            f'<a href="https://jobs.ashbyhq.com/mollie/{job_id}/application">Apply now</a>'
        )
    if "mollie" in url: return f"/vacancies/{ID}"
    return "<html></html>"


class AshbyBatchIndependentQA(unittest.TestCase):
    def test_one_network_failure_does_not_promote_or_block_other_sources(self):
        def fetch(url):
            board=url.rsplit("/",1)[-1]
            if board=="openai": raise TransportError("network failure")
            return good(board)
        result=run_batch(fetch,matching_html)
        self.assertEqual(result["verified_complete"],3)
        self.assertEqual(result["failed"],1)
        failed=[x for x in result["sources"] if x["coverage"]=="unproven"]
        self.assertEqual([x["name"] for x in failed],["OpenAI"])

    def test_schema_change_is_unproven_not_empty_success(self):
        def fetch(url):
            board=url.rsplit("/",1)[-1]
            return {"apiVersion":"2","postings":[]} if board=="mollie" else good(board)
        result=run_batch(fetch,matching_html)
        row=next(x for x in result["sources"] if x["name"]=="Mollie")
        self.assertEqual(row["coverage"],"unproven")
        self.assertFalse(row["exhausted"])
        self.assertIn("AshbyError",row["error"])

    def test_duplicate_and_cross_board_fail_closed(self):
        def fetch(url):
            board=url.rsplit("/",1)[-1]
            if board=="airwallex":
                j=good(board)["jobs"][0]
                return {"apiVersion":"1","jobs":[j,j]}
            if board=="checkout.com":
                return good("other")
            return good(board)
        result=run_batch(fetch,matching_html)
        states={x["name"]:x["coverage"] for x in result["sources"]}
        self.assertEqual(states["Airwallex"],"unproven")
        self.assertEqual(states["Checkout.com"],"unproven")
        self.assertEqual(states["OpenAI"],"verified_complete")
        self.assertEqual(states["Mollie"],"verified_complete")

    def test_unreconciled_first_party_only_job_fails_closed(self):
        extra="00000000-0000-4000-8000-999999999999"
        def html(url):
            if url=="https://jobs.mollie.com/vacancies":
                return f"/vacancies/{ID}\n/vacancies/{extra}"
            if url.endswith(extra):
                return "<html>no matching apply route</html>"
            return matching_html(url)
        result=run_batch(lambda url: good(url.rsplit("/",1)[-1]),html)
        row=next(x for x in result["sources"] if x["name"]=="Mollie")
        self.assertEqual(row["coverage"],"unproven")
        self.assertIn("not live/apply-linked",row["error"])


if __name__=="__main__": unittest.main()
