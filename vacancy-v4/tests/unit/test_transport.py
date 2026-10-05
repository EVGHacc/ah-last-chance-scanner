import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import URLError
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.transport import TransportError,fetch_json

class H:
    def get_content_type(self): return "application/json"
class R:
    status=200;headers=H()
    def __init__(self,b=b'{"jobs":[]}'): self.b=b
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self,n): return self.b[:n]
class TransportDeveloperTests(unittest.TestCase):
    @patch("app.transport.urlopen",return_value=R())
    def test_json(self,_): self.assertEqual(fetch_json("https://example.test")["jobs"],[])
    @patch("app.transport.urlopen",return_value=R(b"x"*11))
    def test_cap(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test",max_bytes=10)
    @patch("app.transport.urlopen",return_value=R(b"bad"))
    def test_bad_json(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")
    @patch("app.transport.time.sleep")
    @patch("app.transport.urlopen",side_effect=[URLError("temporary"),R()])
    def test_transient_network_failure_retries_then_succeeds(self,urlopen,_sleep):
        self.assertEqual(fetch_json("https://example.test",backoff=0)["jobs"],[])
        self.assertEqual(urlopen.call_count,2)
    @patch("app.transport.time.sleep")
    @patch("app.transport.urlopen",side_effect=URLError("down"))
    def test_network_retry_budget_is_bounded(self,urlopen,_sleep):
        with self.assertRaises(TransportError): fetch_json("https://example.test",retries=2,backoff=0)
        self.assertEqual(urlopen.call_count,3)
if __name__=="__main__": unittest.main()
