"""Single-process v4 notification orchestration.

Caller supplies healthy certified matches with independently verified live
official apply URLs. This module does not scan, certify or verify job links.
"""
from .notifications import load_receipts, prepare_strong_match, record_accepted_event
from .resend_dispatch import submit_strong_match
from .notification_attempts import claim_attempt, load_attempts


def dispatch_new_matches(matches, *, receipt_path, api_key, contact_email,
                         submit=submit_strong_match):
    """Send at most one event per source/job key and record provider acceptance.

    matches: iterable of (source_id, Match). A failed or ambiguous submission
    stops the batch, rather than risking further sends without reconciliation.
    A single writer is required for the receipt file.
    """
    receipts = load_receipts(receipt_path)
    sent = set(receipts) | set(load_attempts(receipt_path))
    accepted = []
    for source_id, match in matches:
        notification = prepare_strong_match(match, source_id, sent)
        if notification is None:
            continue
        claim_attempt(receipt_path, notification.key)
        event_id = submit(notification, api_key=api_key, contact_email=contact_email)
        record_accepted_event(receipt_path, notification, event_id)
        sent.add(notification.key)
        accepted.append({"key": notification.key, "event_id": event_id})
    return accepted
