import sys
from pathlib import Path
import unittest
from unittest.mock import patch
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
if __name__=="__main__": unittest.main()
