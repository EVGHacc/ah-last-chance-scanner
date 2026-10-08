"""Pure notification preparation for Vacancy Scanner v4.

This module never sends email. The caller must use the existing Resend
job.strong_match event automation and persist successful dispatch receipts.
"""
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Notification:
    key: str
    event: str
    payload: dict


def prepare_strong_match(match, source: str, sent_keys: set[str]) -> Notification | None:
    """Return an unsent strong-match event; never send duplicates automatically."""
    if not source or not match.job_id or not match.strong:
        return None
    url = urlparse(match.source_url)
    if url.scheme != "https" or not url.netloc or url.username or url.password:
        return None
    key = f"{source}:{match.job_id}"
    if key in sent_keys:
        return None
    return Notification(
        key=key,
        event="job.strong_match",
        payload={
            "ROLE": match.title,
            "EMPLOYER": match.employer,
            "LOCATION": match.location,
            "SCORE": int(match.score),
            "WHY": "; ".join(match.why),
            "LIMITERS": "; ".join(match.limiters),
            "MISMATCH": "; ".join(match.mismatch),
            "SOURCE_URL": match.source_url,
        },
    )
