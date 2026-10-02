import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.model import Coverage, InventoryProof
from app.providers.ashby import inventory
from app.registry import load_sources

URL="https://api.ashbyhq.com/posting-api/job-board/airwallex"


def fetch_json(_):
    req=Request(URL,headers={"User-Agent":"vacancy-v4/1.0","Accept":"application/json"})
    with urlopen(req,timeout=20) as response:
        if response.status != 200: raise RuntimeError(f"HTTP {response.status}")
        return json.load(response)


def main():
    source=next(s for s in load_sources() if s.name=="Airwallex")
    jobs=inventory("airwallex",fetch_json)
    proof=InventoryProof(source,Coverage.VERIFIED_COMPLETE,len(jobs),len(jobs),True,"official_complete_payload")
    proof.validate()
    out={"source":"Airwallex","coverage":proof.coverage.value,"unique_jobs":len(jobs),
         "authoritative_total":len(jobs),"exhausted":True,"evidence_kind":"official_complete_payload","url":URL}
    print(json.dumps(out,sort_keys=True))

if __name__=="__main__": main()
