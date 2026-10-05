from dataclasses import dataclass
from html import unescape
import re
from urllib.parse import urlparse


class GreenhouseError(RuntimeError):
    pass


SUMMARY_LIMIT = 360\nGREENHOUSE_JOB_BOARD_HOSTS = {\n    "boards.greenhouse.io",\n    "job-boards.greenhouse.io",\n    "job-boards.eu.greenhouse.io",\n}\n

@dataclass(frozen=True)
class GreenhouseJob:
    job_id: str
    title: str
    location: str
    summary: str
    job_url: str
    apply_url: str
    department: str = ""
    office: str = ""
    published_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class GreenhouseInventory:
    jobs: tuple[GreenhouseJob, ...]
    authoritative_total: int


def _plain(value) -> str:
    if not isinstance(value, str):
        return ""
    text=value
    for _ in range(2):
        text=unescape(text)
    text=re.sub(r"<[^>]+>"," ",text)
    return re.sub(r"\s+"," ",text).strip()


def short_summary(content: str) -> str:
    text=_plain(content)
    if not text:
        raise GreenhouseError("job content missing")
    sentences=re.split(r"(?<=[.!?])\s+",text)
    summary=""
    for sentence in sentences[:2]:
        candidate=(summary+" "+sentence).strip()
        if len(candidate)>SUMMARY_LIMIT:
            break
        summary=candidate
    if not summary:
        summary=text[:SUMMARY_LIMIT+1]
        if len(summary)>SUMMARY_LIMIT:
            summary=summary[:SUMMARY_LIMIT].rsplit(" ",1)[0].rstrip()+"…"
    return summary


def _host_allowed(url: str, official_domain: str, allowed_domains=(), board_token: str | None = None) -> bool:
    parsed=urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    host=parsed.netloc.lower().split(":",1)[0]
    domains=[official_domain,*allowed_domains]
    if any(host==d.lower() or host.endswith("."+d.lower()) for d in domains):
        return True
    if host in GREENHOUSE_JOB_BOARD_HOSTS and board_token:
        segments=[part for part in parsed.path.split("/") if part]
        return bool(segments) and segments[0].casefold()==board_token.strip().casefold()
    return False


def _first_name(rows, key="name") -> str:
    if not isinstance(rows,list):
        return ""
    for row in rows:
        if isinstance(row,dict) and isinstance(row.get(key),str) and row[key].strip():
            return row[key].strip()
    return ""


def parse_payload(source, board_token: str, payload):
    if not isinstance(payload,dict):
        raise GreenhouseError("structural change: payload is not an object")
    raw_jobs=payload.get("jobs")
    meta=payload.get("meta")
    if not isinstance(raw_jobs,list) or not isinstance(meta,dict):
        raise GreenhouseError("structural change: jobs/meta missing")
    total=meta.get("total")
    if not isinstance(total,int) or total<0:
        raise GreenhouseError("structural change: meta.total missing")
    if len(raw_jobs)!=total:
        raise GreenhouseError(f"authoritative count mismatch: payload={len(raw_jobs)} total={total}")

    jobs={}
    for raw in raw_jobs:
        if not isinstance(raw,dict):
            raise GreenhouseError("structural change: job is not an object")
        ident=raw.get("id")
        title=raw.get("title")
        absolute_url=raw.get("absolute_url")
        content=raw.get("content")
        if not isinstance(ident,(int,str)) or isinstance(ident,bool):
            raise GreenhouseError("structural change: job id missing")
        ident=str(ident).strip()
        if not ident or not isinstance(title,str) or not title.strip():
            raise GreenhouseError("structural change: title missing")
        if not isinstance(absolute_url,str) or not absolute_url.strip():
            raise GreenhouseError("structural change: absolute_url missing")
        if not _host_allowed(
            absolute_url,
            source.official_domain,
            source.allowed_domains,
            board_token=board_token,
        ):
            raise GreenhouseError("job URL does not belong to source or configured Greenhouse board")
        if ident in jobs:
            raise GreenhouseError("duplicate job identity")
        location=""
        if isinstance(raw.get("location"),dict):
            location=_plain(raw["location"].get("name"))
        department=_first_name(raw.get("departments"))
        office=_first_name(raw.get("offices"))
        jobs[ident]=GreenhouseJob(
            job_id=ident,
            title=title.strip(),
            location=location,
            summary=short_summary(content),
            job_url=absolute_url.strip(),
            apply_url=absolute_url.strip(),
            department=department,
            office=office,
            published_at=raw.get("first_published") if isinstance(raw.get("first_published"),str) else None,
            updated_at=raw.get("updated_at") if isinstance(raw.get("updated_at"),str) else None,
        )
    if len(jobs)!=total:
        raise GreenhouseError("unique job count mismatch")
    return GreenhouseInventory(tuple(jobs.values()),total)


def inventory(source, board_token: str, fetch_json):
    if not isinstance(board_token,str) or not board_token.strip():
        raise ValueError("invalid Greenhouse board token")
    payload=fetch_json(board_token)
    return parse_payload(source,board_token,payload)
