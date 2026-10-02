import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.ashby_batch import run_batch
from app.transport import TransportError


def good(board):
    return {"apiVersion":"1","jobs":[{
        "title":"Role",
        "jobUrl":f"https://jobs.ashbyhq.com/{board}/abc",
        "applyUrl":f"https://jobs.ashbyhq.com/{board}/abc/application",
        "isListed":True,
    }]}


class AshbyBatchIndependentQA(unittest.TestCase):
    def test_one_network_failure_does_not_promote_or_block_other_sources(self):
        def fetch(url):
            board=url.rsplit("/",1)[-1]
            if board=="openai": raise TransportError("network failure")
            return good(board)
        result=run_batch(fetch)
        self.assertEqual(result["verified_complete"],3)
        self.assertEqual(result["failed"],1)
        failed=[x for x in result["sources"] if x["coverage"]=="unproven"]
        self.assertEqual([x["name"] for x in failed],["OpenAI"])

    def test_schema_change_is_unproven_not_empty_success(self):
        def fetch(url):
            board=url.rsplit("/",1)[-1]
            return {"apiVersion":"2","postings":[]} if board=="mollie" else good(board)
        result=run_batch(fetch)
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
                j=good("other")["jobs"][0]
                return {"apiVersion":"1","jobs":[j]}
            return good(board)
        result=run_batch(fetch)
        states={x["name"]:x["coverage"] for x in result["sources"]}
        self.assertEqual(states["Airwallex"],"unproven")
        self.assertEqual(states["Checkout.com"],"unproven")
        self.assertEqual(states["OpenAI"],"verified_complete")
        self.assertEqual(states["Mollie"],"verified_complete")


if __name__=="__main__": unittest.main()
