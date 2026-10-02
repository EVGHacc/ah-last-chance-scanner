import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.providers.ashby import AshbyError, inventory


class RateLimited(RuntimeError): pass


class AshbyIndependentQA(unittest.TestCase):
    def test_rate_limit_never_becomes_empty_success(self):
        def fetch(_): raise RateLimited("429")
        with self.assertRaises(RateLimited): inventory("acme",fetch)

    def test_timeout_never_becomes_empty_success(self):
        def fetch(_): raise TimeoutError("network timeout")
        with self.assertRaises(TimeoutError): inventory("acme",fetch)

    def test_schema_change_fails_closed(self):
        with self.assertRaises(AshbyError): inventory("acme",lambda _:{"apiVersion":"2","postings":[]})

    def test_missing_required_field_fails_closed(self):
        raw={"title":"Role","jobUrl":"https://jobs.ashbyhq.com/acme/abc","isListed":True}
        with self.assertRaises(AshbyError): inventory("acme",lambda _:{"apiVersion":"1","jobs":[raw]})

if __name__=="__main__": unittest.main()
