import sys
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.model import Source
from app.runner import ashby_proof
from app.transport import TransportError
from app.providers.ashby import AshbyError

class RunnerIndependentQA(unittest.TestCase):
    def setUp(self):
        self.source=Source("employer","Example","example.com",("https://example.com/jobs",))
    @patch("app.runner.ashby_inventory", side_effect=TransportError("network failure"))
    def test_network_failure(self, _):
        with self.assertRaises(TransportError): ashby_proof(self.source,"Example")
    @patch("app.runner.ashby_inventory", side_effect=TransportError("invalid HTTP response"))
    def test_rate_limit(self, _):
        with self.assertRaises(TransportError): ashby_proof(self.source,"Example")
    @patch("app.runner.ashby_inventory", side_effect=AshbyError("structural change"))
    def test_schema_change(self, _):
        with self.assertRaises(AshbyError): ashby_proof(self.source,"Example")

if __name__=="__main__": unittest.main()
