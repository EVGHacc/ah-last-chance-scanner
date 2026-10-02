import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.ashby_batch import run_batch
from app.transport import TransportError


def good(board):
    ident="00000000-0000-4000-8000-000000000001"
    return {"apiVersion":"1","jobs":[{
        "title":"Role",
        "jobUrl":f"https://jobs.ashbyhq.com/{board}/{ident}",
        "applyUrl":f"https://jobs.ashbyhq.com/{board}/{ident}/application",
        "isListed":True,
    }]}

def matching_html(url):
    ident="00000000-0000-4000-8000-000000000001"
    if "openai" in url: return f"https://jobs.ashbyhq.com/openai/{ident}"
    if "mollie" in url: return f"/vacancies/{ident}"
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

    def test_first_party_count_or_identity_mismatch_fails_closed(self):
        def bad_html(url):
            ident="00000000-0000-4000-8000-999999999999"
            if "mollie" in url: return f"/vacancies/{ident}"
            return matching_html(url)
        result=run_batch(lambda url: good(url.rsplit("/",1)[-1]),bad_html)
        row=next(x for x in result["sources"] if x["name"]=="Mollie")
        self.assertEqual(row["coverage"],"unproven")
        self.assertIn("inventory mismatch",row["error"])


if __name__=="__main__": unittest.main()
