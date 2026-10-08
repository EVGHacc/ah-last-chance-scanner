import json
from datetime import datetime, timezone
from pathlib import Path
DATA=Path(__file__).resolve().parents[1]/"data"
PROOFS=("ashby-proof.json","greenhouse-proof.json","smartrecruiters-proof.json","auditcarriere-proof.json")
MANIFEST=Path(__file__).resolve().parents[1]/"config"/"sources.json"
def manifest_count(path=MANIFEST):
 data=json.loads(Path(path).read_text(encoding="utf-8"))
 sources=data.get("sources")
 if not isinstance(sources,list) or not sources:raise ValueError("invalid v4 manifest: sources must be a nonempty list")
 identities=[(row.get("kind"),row.get("name")) for row in sources]
 if any(not kind or not name for kind,name in identities) or len(set(identities))!=len(sources):raise ValueError("invalid v4 manifest: missing or duplicate source identity")
 if data.get("target_count")!=len(sources):raise ValueError("invalid v4 manifest: target_count disagrees with unique sources")
 return len(sources)
def build(data_dir=DATA,manifest_path=MANIFEST):
 target_count=manifest_count(manifest_path)
 accepted=[];attempted=[]
 for name in PROOFS:
  path=Path(data_dir)/name
  if not path.exists() or not path.read_text(encoding="utf-8").strip():continue
  p=json.loads(path.read_text(encoding="utf-8"));batch_ok=p.get("configured_sources",0)>0 and p.get("failed")==0 and p.get("verified_complete")==p.get("configured_sources")
  for s in p.get("sources",[]):
   row={"provider":p.get("provider"),"name":s.get("name"),"coverage":s.get("coverage"),"unique_jobs":s.get("unique_jobs",0),"checked_at":s.get("checked_at"),"proof_file":name};attempted.append(row);jobs=s.get("jobs")
   valid=batch_ok and row["coverage"]=="verified_complete" and isinstance(jobs,list) and len(jobs)==s.get("unique_jobs") and len({j.get("job_id") for j in jobs})==len(jobs)
   if valid:accepted.append(row)
 return {"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),"target_count":target_count,"accepted_coverage":len(accepted),"accepted_jobs":sum(x["unique_jobs"] for x in accepted),"accepted":accepted,"attempted":attempted}
def main():
 out=build();(DATA/"coverage-ledger.json").write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps({"accepted_coverage":out["accepted_coverage"],"accepted_jobs":out["accepted_jobs"]}))
if __name__=="__main__":main()
