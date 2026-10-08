import json
from pathlib import Path

def _summary(job):
    return str(job.get("short_summary") or job.get("summary") or "").strip()

def validate(path):
    p=json.loads(Path(path).read_text(encoding="utf-8"))
    if p.get("configured_sources",0)<=0 or p.get("failed")!=0 or p.get("verified_complete")!=p.get("configured_sources"):
        raise ValueError("proof batch not fully accepted")
    sources = p.get("sources")
    if not isinstance(sources, list) or len(sources) != p["configured_sources"]:
        raise ValueError("source count mismatch")
    names = [s.get("name") for s in sources if isinstance(s, dict)]
    if len(names) != len(sources) or any(not isinstance(n, str) or not n.strip() for n in names):
        raise ValueError("source identity missing")
    if len(set(names)) != len(names):
        raise ValueError("duplicate source identity")
    for s in sources:
        jobs=s.get("jobs")
        if not isinstance(jobs,list) or len(jobs)!=s.get("unique_jobs"):
            raise ValueError("job count mismatch")
        ids=[j.get("job_id") for j in jobs]
        if len(set(ids))!=len(ids) or any(not x for x in ids):
            raise ValueError("invalid/duplicate job id")
        if any(not str(j.get("title","")).strip() or not _summary(j) or
               not str(j.get("job_url","")).startswith("https://") or
               not str(j.get("apply_url","")).startswith("https://") for j in jobs):
            raise ValueError("job invariant failed")
        if s.get("authoritative_total") is not None and s["authoritative_total"]!=len(jobs):
            raise ValueError("authoritative total mismatch")
    return p
