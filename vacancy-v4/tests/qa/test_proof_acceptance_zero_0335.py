import json,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app.proof_acceptance import validate
class HistoricalZeroInventoryQA(unittest.TestCase):
    def check(self,name,coverage,count):
        payload={"configured_sources":1,"failed":0,"verified_complete":1,"sources":[{"name":name,"coverage":coverage,"unique_jobs":count,"jobs":[]}]}
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"proof.json";path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):validate(path)
    def test_visa_zero(self):self.check("Visa","verified_complete",0)
    def test_remote_zero(self):self.check("Remote.com","verified_complete",0)
    def test_paypal_unproven(self):self.check("PayPal","unproven",0)
if __name__=="__main__":unittest.main()
