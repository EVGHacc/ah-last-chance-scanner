import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.providers.lever import LeverError,inventory
class LeverIndependentQA(unittest.TestCase):
 def test_rate_limit_is_failure(self):
  def fail(*_): raise LeverError('HTTP 429')
  with self.assertRaises(LeverError): inventory('acme',fail)
 def test_timeout_is_failure(self):
  def fail(*_): raise LeverError('network timeout')
  with self.assertRaises(LeverError): inventory('acme',fail)
 def test_schema_change_fails_closed(self):
  with self.assertRaises(LeverError): inventory('acme',lambda *_:{'content':[]})
 def test_missing_fields_fails_closed(self):
  with self.assertRaises(LeverError): inventory('acme',lambda *_:[{'id':'1','text':'Role'}])
if __name__=='__main__': unittest.main()
