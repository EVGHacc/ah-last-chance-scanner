from dataclasses import dataclass
from urllib.parse import urlparse


class AshbyError(RuntimeError):
    pass


@dataclass(frozen=True)
class AshbyJob:
    title: str
    job_url: str
    apply_url: str


def _posting_identity(url: str, board_name: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "jobs.ashbyhq.com":
        raise AshbyError("unexpected job host")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0].casefold() != board_name.casefold():
        raise AshbyError("posting belongs to another board")
    return parts[1].lower()


def inventory(board_name, fetch_json):
    if not isinstance(board_name, str) or not board_name.strip():
        raise ValueError("invalid Ashby board name")
    payload = fetch_json(board_name)
    if not isinstance(payload, dict) or payload.get("apiVersion") != "1":
        raise AshbyError("structural change: invalid apiVersion")
    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list):
        raise AshbyError("structural change: jobs array missing")
    jobs = {}
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            raise AshbyError("structural change: posting is not an object")
        if raw.get("isListed") is False:
            continue
        title, job_url, apply_url = raw.get("title"), raw.get("jobUrl"), raw.get("applyUrl")
        if not all(isinstance(v, str) and v.strip() for v in (title, job_url, apply_url)):
            raise AshbyError("structural change: required posting fields missing")
        ident = _posting_identity(job_url, board_name)
        apply_ident = _posting_identity(apply_url, board_name)
        if apply_ident != ident:
            raise AshbyError("application route belongs to another posting")
        if ident in jobs:
            raise AshbyError("duplicate posting identity")
        jobs[ident] = AshbyJob(title.strip(), job_url, apply_url)
    return tuple(jobs.values())
