from dataclasses import dataclass
from typing import Any, Mapping

class EightfoldError(RuntimeError):
    pass

@dataclass(frozen=True)
class EightfoldJob:
    job_id: str
    title: str
    short_summary: str
    job_url: str
    apply_url: str
    location: str | None = None
    department: str | None = None
    updated_at: str | None = None

def _text(v: Any):
    return v.strip() if isinstance(v, str) and v.strip() else None

def inventory(tenant, fetch_page, page_size=100, max_pages=100):
    if not tenant or page_size < 1:
        raise ValueError("invalid Eightfold configuration")
    jobs = {}
    cursor = None
    for _ in range(max_pages):
        payload = fetch_page(tenant, cursor, page_size)
        if not isinstance(payload, Mapping):
            raise EightfoldError("structural change: expected object")
        rows = payload.get("positions")
        if rows is None:
            rows = payload.get("jobs")
        if not isinstance(rows, list):
            raise EightfoldError("structural change: positions missing")
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise EightfoldError("structural change: position is not object")
            job_id = _text(raw.get("id") or raw.get("positionId"))
            title = _text(raw.get("name") or raw.get("title"))
            summary = _text(raw.get("description") or raw.get("jobDescription"))
            job_url = _text(raw.get("jobUrl") or raw.get("url"))
            apply_url = _text(raw.get("applyUrl") or raw.get("apply_url") or job_url)
            if not all((job_id, title, summary, job_url, apply_url)):
                raise EightfoldError("structural change: required position fields missing")
            if job_id in jobs:
                raise EightfoldError("duplicate position id")
            jobs[job_id] = EightfoldJob(
                job_id, title, summary[:500], job_url, apply_url,
                _text(raw.get("location")), _text(raw.get("department")),
                _text(raw.get("updatedAt") or raw.get("updated_at")))
        nxt = payload.get("nextCursor") or payload.get("next_cursor")
        if not nxt:
            return tuple(jobs.values())
        if nxt == cursor:
            raise EightfoldError("pagination cursor did not advance")
        cursor = nxt
    raise EightfoldError("pagination cap reached before exhaustion")
