#!/usr/bin/env python3
"""Read-only monitor for the single scheduled AH production session."""
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
ACTIVE = ("queued", "in_progress", "waiting", "pending", "requested")
MONITOR_START = 17 * 60 + 30
MONITOR_END = 22 * 60 + 30
MAX_SCAN_AGE = 240
REQUIRED_STORES = {1463, 1348, 1135, 4046, 8728}


def valid_heartbeat(status, now):
    """Validate the latest published scan; this is not a process heartbeat."""
    if not isinstance(status, dict) or status.get("date") != now.date().isoformat():
        return False
    if status.get("authMode") != "user-refresh":
        return False
    if status.get("rawExpected") != 101 or status.get("canonicalExpected") != 61:
        return False
    if status.get("category") != "Vlees":
        return False
    try:
        stores = {int(value) for value in status.get("stores", [])}
    except (TypeError, ValueError):
        return False
    if not REQUIRED_STORES.issubset(stores):
        return False
    latest = status.get("latestValid") or {}
    if (latest.get("authMode") != "user-refresh"
            or latest.get("rawScheduledSlot") != "22:30"
            or latest.get("status") not in ("OK", "OK_ZERO_ROWS")):
        return False
    try:
        checked = datetime.fromisoformat(latest["checkedAt"])
    except (KeyError, TypeError, ValueError):
        return False
    if checked.tzinfo is None:
        return False
    age = (now - checked.astimezone(TZ)).total_seconds()
    return 0 <= age <= MAX_SCAN_AGE


def expected_slots(step):
    return {
        f"{minute // 60:02d}:{minute % 60:02d}"
        for minute in range(MONITOR_START, MONITOR_END + 1, step)
    }


def valid_final_publication(status, now):
    """Require the complete same-day final publication after the live window."""
    if not isinstance(status, dict) or status.get("date") != now.date().isoformat():
        return False
    if (status.get("authMode") != "user-refresh" or status.get("category") != "Vlees"
            or status.get("rawExpected") != 101 or status.get("canonicalExpected") != 61):
        return False
    try:
        stores = {int(value) for value in status.get("stores", [])}
    except (TypeError, ValueError):
        return False
    if stores != REQUIRED_STORES:
        return False
    raw_seen = status.get("rawSeen")
    canonical_seen = status.get("canonicalSeen")
    if (not isinstance(raw_seen, list) or len(raw_seen) != 101
            or any(not isinstance(slot, str) for slot in raw_seen)
            or len(set(raw_seen)) != 101 or set(raw_seen) != expected_slots(3)):
        return False
    if (not isinstance(canonical_seen, list) or len(canonical_seen) != 61
            or any(not isinstance(slot, str) for slot in canonical_seen)
            or len(set(canonical_seen)) != 61 or set(canonical_seen) != expected_slots(5)):
        return False
    if status.get("rawMissing") or status.get("canonicalMissing"):
        return False
    latest = status.get("latestValid") or {}
    if latest.get("authMode") != "user-refresh":
        return False
    try:
        checked = datetime.fromisoformat(latest["checkedAt"])
    except (KeyError, TypeError, ValueError):
        return False
    if checked.tzinfo is None:
        return False
    checked = checked.astimezone(TZ)
    final_slot = checked.replace(hour=22, minute=30, second=0, microsecond=0)
    age_after_final_slot = (checked - final_slot).total_seconds()
    return (checked.date() == now.date() and checked <= now
            and 0 <= age_after_final_slot <= MAX_SCAN_AGE)


def active_runs(runs, now):
    """Return today's active primary-session runs; never mutate Actions state."""
    result = []
    for run in runs:
        if run.get("event") != "schedule" or run.get("status") not in ACTIVE:
            continue
        try:
            created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if created.astimezone(TZ).date() == now.date():
            result.append(run)
    return result


def decision(status, runs, now):
    minute = now.hour * 60 + now.minute
    if minute < MONITOR_START:
        return "IDLE"
    if minute > MONITOR_END:
        return "COMPLETE" if valid_final_publication(status, now) else "ALARM"
    if not active_runs(runs, now) or not valid_heartbeat(status, now):
        return "ALARM"
    return "HEALTHY"


def api(path):
    """GET-only GitHub API client. No cancel or dispatch capability exists."""
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}/{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ah-read-only-session-watchdog",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def read_status():
    try:
        return json.loads(Path("data/status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    now = datetime.now(TZ)
    minute = now.hour * 60 + now.minute
    status = read_status()
    if minute < MONITOR_START:
        print("IDLE: before Amsterdam monitoring window")
        return 0
    if minute > MONITOR_END:
        state = decision(status, [], now)
        print(f"{state}: final publication audit at {now.isoformat()}")
        if state == "ALARM":
            print("::error::AH final publication is missing, stale or incomplete")
            return 1
        return 0
    runs = api("actions/workflows/session.yml/runs?per_page=50").get("workflow_runs", [])
    state = decision(status, runs, now)
    print(f"{state}: read-only session watchdog at {now.isoformat()}")
    if state == "ALARM":
        print("::error::AH production session or latest authenticated scan is missing/stale")
        return 1
    return 0


def self_test():
    now = datetime(2026, 11, 2, 18, 0, tzinfo=TZ)
    good = {
        "date": "2026-11-02",
        "authMode": "user-refresh",
        "rawExpected": 101,
        "canonicalExpected": 61,
        "category": "Vlees",
        "stores": [1463, 1348, 1135, 4046, 8728],
        "latestValid": {
            "authMode": "user-refresh",
            "checkedAt": "2026-11-02T17:59:00+01:00",
        },
    }
    active = [{
        "event": "schedule",
        "status": "in_progress",
        "created_at": "2026-11-02T16:55:00Z",
    }]
    assert decision(good, active, now) == "HEALTHY"
    assert decision(good, [], now) == "ALARM"
    assert decision({}, active, now) == "ALARM"
    assert decision({}, [], datetime(2026, 11, 2, 23, 0, tzinfo=TZ)) == "ALARM"
    assert not hasattr(api, "post")
    print("Read-only watchdog self-test: PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        raise SystemExit(main())
