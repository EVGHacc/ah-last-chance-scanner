import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from .model import Coverage
from .providers.eightfold import inventory
from .registry import load_sources
from .transport import fetch_json

DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/"config"/"eightfold_sources.json"
MAX_BYTES=16_000_000

def load_config(path=DEFAULT_CONFIG):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version")!=1 or data.get("provider")!="eightfold":
        raise ValueError("invalid Eightfold config")
    rows=data.get("sources")
    if not isinstance(rows,list) or not rows:
        raise ValueError("Eightfold config has no sources")
    return rows

def run_batch(fetcher=None,config_path=DEFAULT_CONFIG):
    targets={s.name:s for s in load_sources()}; rows=load_config(config_path)
    unknown=[r["name"] for r in rows if r["name"] not in targets]
    if unknown:
        raise ValueError(f"Eightfold config references non-target sources: {unknown}")
    results=[]
    for row in rows:
        checked_at=datetime.now(timezone.utc).isoformat()
        endpoint=row.get("public_inventory_endpoint")
        try:
            if not endpoint:
                raise RuntimeError("BLOCKED: no first-party public authoritative Eightfold inventory endpoint proven")
            transport=fetcher or (lambda url: fetch_json(url,max_bytes=MAX_BYTES))
            def page(tenant,cursor,size):
                sep="&" if "?" in endpoint else "?"
                url=f"{endpoint}{sep}limit={size}"
                if cursor is not None:
                    url+=f"&cursor={cursor}"
                return transport(url)
            jobs=inventory(row["tenant"],page)
            records=[{"job_id":j.job_id,"title":j.title,"short_summary":j.short_summary,
                      "job_url":j.job_url,"apply_url":j.apply_url,"location":j.location,
                      "department":j.department,"updated_at":j.updated_at} for j in jobs]
            if len(records)!=len({j["job_id"] for j in records}):
                raise ValueError("persisted inventory mismatch")
            digest=hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            results.append({"name":row["name"],"coverage":Coverage.VERIFIED_COMPLETE.value,
                            "unique_jobs":len(records),"jobs_sha256":digest,"jobs":records,
                            "checked_at":checked_at,"error":None})
        except Exception as exc:
            results.append({"name":row["name"],"coverage":Coverage.UNPROVEN.value,
                            "unique_jobs":0,"jobs_sha256":None,"jobs":[],"checked_at":checked_at,
                            "error":f"{type(exc).__name__}: {exc}"})
    verified=sum(x["coverage"]==Coverage.VERIFIED_COMPLETE.value for x in results)
    return {"schema_version":1,"provider":"eightfold","configured_sources":len(results),
            "verified_complete":verified,"failed":len(results)-verified,"sources":results}
