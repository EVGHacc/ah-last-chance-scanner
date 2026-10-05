import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin
from .model import Coverage
from .registry import load_sources
from .transport import fetch_json

DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/"config"/"eightfold_sources.json"
MAX_BYTES=16_000_000
PAGE_SIZE=10
MAX_PAGES=5000
EIGHTFOLD_RETRIES=5
EIGHTFOLD_BACKOFF=2.0

def load_config(path=DEFAULT_CONFIG):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version")!=1 or data.get("provider")!="eightfold":
        raise ValueError("invalid Eightfold config")
    rows=data.get("sources")
    if not isinstance(rows,list) or not rows:
        raise ValueError("Eightfold config has no sources")
    return rows

def _text(v):
    return v.strip() if isinstance(v,str) and v.strip() else None

def _pcsx_inventory(row, transport):
    search=row.get("pcsx_search_endpoint")
    details=row.get("pcsx_details_endpoint")
    domain=row.get("domain")
    careers=row.get("careers_url")
    if not all((search,details,domain,careers)):
        raise RuntimeError("BLOCKED: no complete first-party PCSX authority contract proven")
    records=[]; seen=set(); expected=None
    for page in range(MAX_PAGES):
        start=page*PAGE_SIZE
        url=f"{search}?domain={quote(domain)}&query=&location=&start={start}&num={PAGE_SIZE}"
        payload=transport(url)
        data=payload.get("data") if isinstance(payload,dict) else None
        if not isinstance(data,dict) or not isinstance(data.get("positions"),list):
            raise RuntimeError("structural change: PCSX data.positions missing")
        try:
            count=int(data.get("count"))
        except (TypeError,ValueError):
            raise RuntimeError("structural change: PCSX authoritative count missing")
        if expected is None: expected=count
        elif count!=expected: raise RuntimeError("PCSX authoritative count changed during pagination")
        rows=data["positions"]
        for raw in rows:
            if not isinstance(raw,dict): raise RuntimeError("structural change: PCSX position is not object")
            jid=_text(str(raw.get("id"))) if raw.get("id") is not None else None
            title=_text(raw.get("name") or raw.get("title"))
            path=_text(raw.get("positionUrl"))
            if not all((jid,title,path)): raise RuntimeError("structural change: PCSX required search fields missing")
            if jid in seen: raise RuntimeError("duplicate position id")
            seen.add(jid)
            detail_url=f"{details}?position_id={quote(jid)}&domain={quote(domain)}&hl=en"
            detail_payload=transport(detail_url)
            detail=detail_payload.get("data") if isinstance(detail_payload,dict) else None
            if not isinstance(detail,dict): raise RuntimeError("structural change: PCSX position details missing")
            summary=_text(detail.get("jobDescription") or detail.get("description"))
            if not summary: raise RuntimeError("structural change: PCSX job description missing")
            job_url=urljoin(careers,path)
            locations=raw.get("locations") or raw.get("standardizedLocations") or []
            location="; ".join(str(x) for x in locations if x) if isinstance(locations,list) else _text(locations)
            records.append({"job_id":jid,"title":title,"short_summary":summary[:500],
                "job_url":job_url,"apply_url":job_url,"location":location or None,
                "department":_text(raw.get("department")),"updated_at":_text(str(raw.get("postedTs"))) if raw.get("postedTs") is not None else None})
        if len(records)>=expected:
            if len(records)!=expected: raise RuntimeError("PCSX inventory exceeds authoritative count")
            return records
        if len(rows)!=PAGE_SIZE: raise RuntimeError("PCSX pagination ended before authoritative count")
    raise RuntimeError("PCSX pagination cap reached before exhaustion")

def run_batch(fetcher=None,config_path=DEFAULT_CONFIG):
    targets={s.name:s for s in load_sources()}; rows=load_config(config_path)
    unknown=[r["name"] for r in rows if r["name"] not in targets]
    if unknown: raise ValueError(f"Eightfold config references non-target sources: {unknown}")
    results=[]
    for row in rows:
        checked_at=datetime.now(timezone.utc).isoformat()
        try:
            transport=fetcher or (lambda url: fetch_json(url,max_bytes=MAX_BYTES,retries=EIGHTFOLD_RETRIES,backoff=EIGHTFOLD_BACKOFF))
            records=_pcsx_inventory(row,transport)
            if len(records)!=len({j["job_id"] for j in records}): raise ValueError("persisted inventory mismatch")
            digest=hashlib.sha256(json.dumps(records,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            results.append({"name":row["name"],"coverage":Coverage.VERIFIED_COMPLETE.value,
                "unique_jobs":len(records),"jobs_sha256":digest,"jobs":records,"checked_at":checked_at,"error":None})
        except Exception as exc:
            results.append({"name":row["name"],"coverage":Coverage.UNPROVEN.value,
                "unique_jobs":0,"jobs_sha256":None,"jobs":[],"checked_at":checked_at,"error":f"{type(exc).__name__}: {exc}"})
    verified=sum(x["coverage"]==Coverage.VERIFIED_COMPLETE.value for x in results)
    return {"schema_version":1,"provider":"eightfold","configured_sources":len(results),
        "verified_complete":verified,"failed":len(results)-verified,"sources":results}
