import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from app.providers.lever import LeverError,inventory

def job(i): return {'id':str(i),'text':f'Job {i}','hostedUrl':f'https://jobs.eu.lever.co/acme/{i}'}
class LeverUnitTests(unittest.TestCase):
 def test_exhausts(self):
  def page(site,offset,limit): return [job(0),job(1)] if offset==0 else [job(2)]
  self.assertEqual(len(inventory('acme',page,limit=2)),3)
 def test_duplicate_fails_closed(self):
  with self.assertRaises(LeverError): inventory('acme',lambda *_:[job(1),job(1)],limit=2)
 def test_cap_fails_closed(self):
  with self.assertRaises(LeverError): inventory('acme',lambda s,o,l:[job(o)],limit=1,max_pages=2)
if __name__=='__main__': unittest.main()
