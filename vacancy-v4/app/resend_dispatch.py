"""Resend event transport for Vacancy Scanner v4.

Only event submission; the existing Resend automation owns email delivery.
"""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


class DispatchError(RuntimeError):
    pass


def submit_strong_match(notification, *, api_key: str, contact_email: str, opener=urlopen) -> str:
    """Submit an existing strong-match event and return its accepted event ID.

    A returned event ID confirms API acceptance, not completed email delivery.
    Caller owns durable receipts and retries; never retry blindly on ambiguous
    network failures because the provider may already have accepted the event.
    """
    if notification.event != "job.strong_match":
        raise ValueError("Unsupported event")
    if not api_key or not contact_email:
        raise ValueError("Resend credentials and recipient are required")
    data = json.dumps({
        "event": notification.event,
        "email": contact_email,
        "payload": notification.payload,
    }).encode("utf-8")
    request = Request(
        "https://api.resend.com/events",
        data=data,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=20) as response:
            status = response.status
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise DispatchError("Event submission failed; inspect provider before retry") from exc
    except (ValueError, UnicodeError) as exc:
        raise DispatchError("Malformed provider response; inspect before retry") from exc
    if status < 200 or status >= 300 or not isinstance(body, dict):
        raise DispatchError("Provider did not accept event")
    event_id = body.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise DispatchError("Provider response lacks event ID")
    return event_id
