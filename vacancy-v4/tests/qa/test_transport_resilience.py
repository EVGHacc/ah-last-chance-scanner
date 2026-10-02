import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.transport import TransportError,fetch_json

class H:
    def get_content_type(self): return "text/html"
class Html:
    status=200;headers=H()
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self,n): return b"<html/>"
class TransportIndependentQA(unittest.TestCase):
    @patch("app.transport.urlopen",side_effect=HTTPError("https://x",429,"rate",{},None))
    def test_rate_limit(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")
    @patch("app.transport.urlopen",side_effect=URLError("timeout"))
    def test_network(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")
    @patch("app.transport.urlopen",return_value=Html())
    def test_structural_content_type_change(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")
if __name__=="__main__": unittest.main()
