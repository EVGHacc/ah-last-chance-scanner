from dataclasses import dataclass
from typing import Any, Mapping, Optional


class LeverError(RuntimeError):
    pass


@dataclass(frozen=True)
class LeverJob:
    job_id: str
    title: str
    short_summary: str
    job_url: str
    apply_url: str
    location: Optional[str] = None
    department: Optional[str] = None
    team: Optional[str] = None
    office: Optional[str] = None
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _summary(raw: Mapping[str, Any]) -> Optional[str]:
    description = _text(raw.get("descriptionPlain")) or _text(raw.get("description"))
    if description:
        return description[:500]
    lists = raw.get("lists")
    if isinstance(lists, list):
        parts = []
        for item in lists:
            if isinstance(item, Mapping):
                part = _text(item.get("text")) or _text(item.get("content"))
                if part:
                    parts.append(part)
        if parts:
            return " ".join(parts)[:500]
    return None


def _category(raw: Mapping[str, Any], name: str) -> Optional[str]:
    categories = raw.get("categories")
    return _text(categories.get(name)) if isinstance(categories, Mapping) else None


def inventory(site, fetch_page, limit=100, max_pages=100):
    if not site or not 1 <= limit <= 100:
        raise ValueError("invalid Lever configuration")
    jobs = {}
    offset = 0
    for _ in range(max_pages):
        payload = fetch_page(site, offset, limit)
        if not isinstance(payload, list):
            raise LeverError("structural change: expected JSON array")
        for raw in payload:
            if not isinstance(raw, Mapping):
                raise LeverError("structural change: posting is not an object")
            job_id = _text(raw.get("id"))
            title = _text(raw.get("text"))
            job_url = _text(raw.get("hostedUrl"))
            apply_url = _text(raw.get("applyUrl"))
            summary = _summary(raw)
            if not all((job_id, title, summary, job_url, apply_url)):
                raise LeverError("structural change: required posting fields missing")
            if job_id in jobs:
                raise LeverError("duplicate/page-wrap detected")
            jobs[job_id] = LeverJob(
                job_id=job_id,
                title=title,
                short_summary=summary,
                job_url=job_url,
                apply_url=apply_url,
                location=_category(raw, "location"),
                department=_category(raw, "department"),
                team=_category(raw, "team"),
                office=_category(raw, "office"),
                created_at=raw.get("createdAt") if isinstance(raw.get("createdAt"), int) else None,
                updated_at=raw.get("updatedAt") if isinstance(raw.get("updatedAt"), int) else None,
            )
        if len(payload) < limit:
            return tuple(jobs.values())
        offset += len(payload)
    raise LeverError("pagination cap reached before exhaustion")
