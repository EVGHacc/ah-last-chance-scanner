import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .model import Coverage
from .providers.smartrecruiters import inventory
from .registry import load_sources
from .transport import fetch_json

DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/"config"/"smartrecruiters_sources.json"
DEFAULT_OUTPUT=Path(__file__).resolve().parents[1]/"data"/"smartrecruiters-proof.json"
MAX_BYTES=16_000_000

def load_config(path=DEFAULT_CONFIG):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version")!=1 or data.get("provider")!="smartrecruiters": raise ValueError("invalid SmartRecruiters config")
    rows=data.get("sources")
    if not isinstance(rows,list) or not rows: raise ValueError("SmartRecruiters config has no sources")
    seen=set()
    for row in rows:
        if set(row)!={"name","company_identifier","first_party_evidence_url"}: raise ValueError("unexpected SmartRecruiters config fields")
        if not all(isinstance(v,str) and v.strip() for v in row.values()): raise ValueError("invalid SmartRecruiters config value")
        if row["name"] in seen: raise ValueError("duplicate SmartRecruiters source")
        seen.add(row["name"])
    return rows

def _record(j):
    return {"job_id":j.job_id,"title":j.title,"summary":j.summary,"job_url":j.job_url,"apply_url":j.apply_url,"record_source":"smartrecruiters_posting_api"}

def run_batch(fetcher=None,config_path=DEFAULT_CONFIG):
    targets={s.name:s for s in load_sources()}; rows=load_config(config_path)
    unknown=[r["name"] for r in rows if r["name"] not in targets]
    if unknown: raise ValueError(f"SmartRecruiters config references non-target sources: {unknown}")
    transport=fetcher or (lambda url: fetch_json(url,max_bytes=MAX_BYTES)); results=[]
    for row in rows:
        checked_at=datetime.now(timezone.utc).isoformat()
        try:
            jobs,total=inventory(row["company_identifier"],transport)
            records=sorted((_record(j) for j in jobs),key=lambda j:(j["title"].casefold(),j["job_id"]))
            if len(records)!=total or len({j["job_id"] for j in records})!=len(records): raise ValueError("persisted inventory mismatch")
            digest=hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            results.append({"name":row["name"],"company_identifier":row["company_identifier"],"coverage":Coverage.VERIFIED_COMPLETE.value,"unique_jobs":len(records),"authoritative_total":total,"exhausted":True,"evidence_kind":"smartrecruiters_totalFound_reconciled","first_party_evidence_url":row["first_party_evidence_url"],"jobs_sha256":digest,"jobs":records,"checked_at":checked_at,"error":None})
        except Exception as exc:
            results.append({"name":row["name"],"company_identifier":row["company_identifier"],"coverage":Coverage.UNPROVEN.value,"unique_jobs":0,"authoritative_total":None,"exhausted":False,"evidence_kind":None,"first_party_evidence_url":row["first_party_evidence_url"],"jobs_sha256":None,"jobs":[],"checked_at":checked_at,"error":f"{type(exc).__name__}: {exc}"})
    verified=sum(x["coverage"]==Coverage.VERIFIED_COMPLETE.value for x in results)
    return {"schema_version":1,"provider":"smartrecruiters","generated_at":datetime.now(timezone.utc).isoformat(),"configured_sources":len(results),"verified_complete":verified,"failed":len(results)-verified,"sources":results}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,default=DEFAULT_OUTPUT); a=p.parse_args()
    result=run_batch(); a.output.parent.mkdir(parents=True,exist_ok=True)
    target=a.output if result["failed"]==0 else a.output.with_suffix(a.output.suffix+".attempt")
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"provider":"smartrecruiters","configured_sources":result["configured_sources"],"verified_complete":result["verified_complete"],"failed":result["failed"],"persisted_jobs":sum(len(x["jobs"]) for x in result["sources"])}))
    if result["failed"]: raise SystemExit(1)
if __name__=="__main__": main()
