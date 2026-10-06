import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from .model import Coverage
from .registry import load_sources
from .transport import fetch_text
from .providers.auditcarriere import inventory
DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/"config"/"auditcarriere_sources.json"
MAX_BYTES=16_000_000
def load_config(path=DEFAULT_CONFIG):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version")!=1 or data.get("provider")!="auditcarriere": raise ValueError("invalid AuditCarriere config")
    rows=data.get("sources")
    if not isinstance(rows,list) or not rows: raise ValueError("AuditCarriere config has no sources")
    for row in rows:
        if set(row)!={"name","listing_url_template","first_party_evidence_url"}: raise ValueError("unexpected AuditCarriere config fields")
    return rows
def run_batch(fetcher=None,config_path=DEFAULT_CONFIG):
    targets={s.name:s for s in load_sources()}; rows=load_config(config_path); results=[]
    transport=fetcher or (lambda url: fetch_text(url,max_bytes=MAX_BYTES))
    for row in rows:
        checked_at=datetime.now(timezone.utc).isoformat()
        try:
            if row["name"] not in targets: raise ValueError("config references non-target source")
            inv=inventory(row["listing_url_template"],transport); records=list(inv.jobs)
            if len(records)!=inv.authoritative_total or len({j["job_id"] for j in records})!=len(records): raise ValueError("persisted inventory mismatch")
            if any(not j["title"].strip() or not j["short_summary"].strip() or not j["job_url"].startswith("http") or not j["apply_url"].startswith("http") for j in records): raise ValueError("job invariant failed")
            digest=hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            results.append({"name":row["name"],"coverage":Coverage.VERIFIED_COMPLETE.value,"unique_jobs":len(records),"authoritative_total":inv.authoritative_total,"exhausted":True,"evidence_kind":"auditcarriere_visible_total_reconciled","first_party_evidence_url":row["first_party_evidence_url"],"jobs_sha256":digest,"jobs":records,"checked_at":checked_at,"error":None})
        except Exception as exc:
            results.append({"name":row["name"],"coverage":Coverage.UNPROVEN.value,"unique_jobs":0,"authoritative_total":None,"exhausted":False,"evidence_kind":None,"first_party_evidence_url":row["first_party_evidence_url"],"jobs_sha256":None,"jobs":[],"checked_at":checked_at,"error":f"{type(exc).__name__}: {exc}"})
    verified=sum(x["coverage"]==Coverage.VERIFIED_COMPLETE.value for x in results)
    return {"schema_version":1,"provider":"auditcarriere","generated_at":datetime.now(timezone.utc).isoformat(),"configured_sources":len(results),"verified_complete":verified,"failed":len(results)-verified,"sources":results}
