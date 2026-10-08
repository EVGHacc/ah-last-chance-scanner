"""Deterministic feedback join for vacancy reports; no network or writes."""


def _source_identity(source):
    value = str(source or "").strip().casefold()
    for prefix in ("employer::", "recruiter::"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


def history_for_job(feedback, source, job_id):
    """Join link and reply feedback by source/job identity, preserving chronology."""
    expected = _source_identity(source)
    job = str(job_id)
    history, seen = [], set()
    for row in feedback:
        if not isinstance(row, dict):
            raise ValueError("feedback row must be an object")
        if _source_identity(row.get("source")) != expected or str(row.get("job_id")) != job:
            continue
        message_id = row.get("message_id")
        if message_id and message_id in seen:
            continue
        if message_id:
            seen.add(message_id)
        history.append(row)
    return sorted(history, key=lambda item: str(item.get("received_at") or ""))
