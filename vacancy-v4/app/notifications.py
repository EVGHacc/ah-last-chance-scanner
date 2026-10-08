"""Pure notification preparation for Vacancy Scanner v4.

No email is sent by importing this module. The caller must use the existing
Resend job.strong_match automation and persist accepted event receipts.
"""
from dataclasses import dataclass
from urllib.parse import urlparse
import json
from pathlib import Path
from datetime import datetime, timezone


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


def load_receipts(path: str | Path) -> dict:
    """Read persisted accepted-event receipts; fail closed on corruption."""
    path = Path(path)
    if not path.exists():
        return {}
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, dict):
        raise ValueError("Notification receipt ledger must be a JSON object")
    return records


def record_accepted_event(path: str | Path, notification: Notification, event_id: str):
    """Record an API-accepted event, not an email-delivery confirmation.

    The caller must only invoke this after a successful Resend API response.
    Atomic replacement avoids partial JSON files; concurrent writers still
    require a single-writer lock or transactional backing store.
    """
    if not event_id:
        raise ValueError("Cannot record event without a provider event ID")
    path = Path(path)
    receipts = load_receipts(path)
    if notification.key in receipts:
        raise ValueError("Event already recorded; refusing duplicate receipt")
    receipts[notification.key] = {
        "event": notification.event,
        "event_id": event_id,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(receipts, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
