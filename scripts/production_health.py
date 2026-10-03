#!/usr/bin/env python3
"""Production readiness/health state for the AH scanner."""
import json, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Amsterdam")
REQUIRED={"1463","1348","1135","4046","8728"}

def load(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return {}

def state(now=None):
    now=now or datetime.now(TZ)
    status=load("data/status.json")
    minute=now.hour*60+now.minute
    if minute < 17*60+30:
        return "READY" if status else "AMBER"
    if status.get("date") != now.date().isoformat():
        return "RED"
    latest=status.get("latestValid") or {}
    try: checked=datetime.fromisoformat(latest["checkedAt"]).astimezone(TZ)
    except Exception: return "RED"
    age=(now-checked).total_seconds()
    if age <= 45: return "GREEN"
    if age <= 60: return "AMBER"
    if age <= 180: return "RED"
    return "CRITICAL"

def validate_preflight():
    # Static production invariants that can be proved before the first slot.
    import session
    assert session.MAX_RECOVERY_AGE==240
    assert session.RECOVERY_START_DEADLINE<=205
    assert len([p for p in session.points_for(datetime(2026,10,3,tzinfo=TZ))
                if session.raw_due(p.hour*60+p.minute)])==101
    assert len([p for p in session.points_for(datetime(2026,10,3,tzinfo=TZ))
                if session.canonical_due(p.hour*60+p.minute)])==61
    print("PRE-FLIGHT PASS: cadence/recovery invariants valid")

def self_test():
    assert state(datetime(2026,10,3,17,0,tzinfo=TZ)) in {"READY","AMBER"}
    validate_preflight()
    print("Production health self-test: PASS")

if __name__=="__main__":
    if "--self-test" in sys.argv: self_test()
    elif "--preflight" in sys.argv: validate_preflight()
    else:
        s=state(); print(s)
        if s in {"RED","CRITICAL"}: raise SystemExit(2)
