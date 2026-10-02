import json
from datetime import datetime, timezone
from pathlib import Path
DATA=Path(__file__).resolve().parents[1]/"data"
PROOFS=("ashby-proof.json","greenhouse-proof.json","smartrecruiters-proof.json")
def build(data_dir=DATA):
 accepted=[];attempted=[]
 for name in PROOFS:
  path=Path(data_dir)/name
  if not path.exists() or not path.read_text(encoding="utf-8").strip():continue
  p=json.loads(path.read_text(encoding="utf-8"))
  batch_ok=p.get("configured_sources",0)>0 and p.get("failed")==0 and p.get("verified_complete")==p.get("configured_sources")
  for s in p.get("sources",[]):
   row={"provider":p.get("provider"),"name":s.get("name"),"coverage":s.get("coverage"),"unique_jobs":s.get("unique_jobs",0),"checked_at":s.get("checked_at"),"proof_file":name};attempted.append(row)
   jobs=s.get("jobs")
   valid=batch_ok and row["coverage"]=="verified_complete" and isinstance(jobs,list) and len(jobs)==s.get("unique_jobs") and len({j.get("job_id") for j in jobs})==len(jobs)
   if valid:accepted.append(row)
 return {"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"target_count":104,"accepted_coverage":len(accepted),"accepted_jobs":sum(x["unique_jobs"] for x in accepted),"accepted":accepted,"attempted":attempted}
def main():
 out=build();(DATA/"coverage-ledger.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps({"accepted_coverage":out["accepted_coverage"],"accepted_jobs":out["accepted_jobs"]}))
if __name__=="__main__":main()
