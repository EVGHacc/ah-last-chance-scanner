import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.transport import TransportError,fetch_json

class H:
    def __init__(self,content_type="text/html"): self.content_type=content_type
    def get_content_type(self): return self.content_type
class Response:
    status=200
    def __init__(self,b=b"<html/>",content_type="text/html"):
        self.b=b; self.headers=H(content_type)
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def read(self,n): return self.b[:n]

class TransportIndependentQA(unittest.TestCase):
    @patch("app.transport.urlopen",side_effect=HTTPError("https://x",429,"rate",{},None))
    def test_rate_limit(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")

    @patch("app.transport.urlopen",side_effect=URLError("timeout"))
    def test_network(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")

    @patch("app.transport.urlopen",return_value=Response())
    def test_structural_content_type_change(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")

    @patch("app.transport.urlopen",return_value=Response(b"x"*11,"application/json"))
    def test_oversized_payload_fails_closed(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test",max_bytes=10)

    @patch("app.transport.urlopen",return_value=Response(b"{bad","application/json"))
    def test_malformed_json_fails_closed(self,_):
        with self.assertRaises(TransportError): fetch_json("https://example.test")

if __name__=="__main__": unittest.main()
