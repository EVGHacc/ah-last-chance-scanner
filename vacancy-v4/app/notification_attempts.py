"""Crash-safe local outbox claims; a single persistent writer is required."""
import json
from datetime import datetime, timezone
from pathlib import Path


def pending_path(receipt_path):
    path=Path(receipt_path)
    return path.with_name(path.name+".pending.json")


def load_attempts(receipt_path):
    path=pending_path(receipt_path)
    if not path.exists():
        return {}
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict):
        raise ValueError("invalid pending notification ledger")
    return data


def claim_attempt(receipt_path,key):
    """Persist before network submission; unknown outcomes require reconciliation."""
    attempts=load_attempts(receipt_path)
    if key in attempts:
        raise ValueError("notification already attempted")
    attempts[key]={"status":"in_flight","claimed_at":datetime.now(timezone.utc).isoformat()}
    path=pending_path(receipt_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+".tmp")
    tmp.write_text(json.dumps(attempts,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    tmp.replace(path)
