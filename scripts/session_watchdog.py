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


def heartbeat_age_seconds(status, now):
    """Return age of the latest authenticated scan heartbeat, or None if invalid."""
    if not isinstance(status, dict) or status.get("date") != now.date().isoformat():
        return None
    latest = status.get("latestValid") or {}
    try:
        checked = datetime.fromisoformat(latest["checkedAt"])
    except (KeyError, TypeError, ValueError):
        return None
    if checked.tzinfo is None:
        return None
    age = (now - checked.astimezone(TZ)).total_seconds()
    return age if 0 <= age <= MAX_SCAN_AGE else None


def valid_heartbeat(status, now):
    """Validate the published authenticated-scan heartbeat (not a process heartbeat).""
    if not isinstance(status, dict) or status.get("date") != now.date().isoformat():
        return False
    if status.get("authMode") != "user-refresh":
        return False
    if status.get("rawExpected") != 101 or status.get("canonicalExpected") != 61:
        return False
    if status.get("category") != "Vlees":
        return False
    stores = {int(value) for value in status.get("stores", [])}
    if not REQUIRED_STORES.issubset(stores):
        return False
    latest = status.get("latestValid") or {}
    if latest.get("authMode") != "user-refresh":
        return False
    return heartbeat_age_seconds(status, now) is not None


def circuit_state(runs, now):
    """Read-only breaker: two consecutive failed scheduled runs open the circuit."""
    today = []
    for run in runs:
        if run.get("event") != "schedule":
            continue
        try:
            created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if created.astimezone(TZ).date() == now.date():
            today.append((created, run))
    today.sort(key=lambda item: item[0], reverse=True)
    if not today:
        return "CLOSED"
    if today[0][1].get("status") in ACTIVE:
        return "HALF_OPEN"
    failures = {"failure", "timed_out", "cancelled", "action_required"}
    streak = 0
    for _, run in today:
        if run.get("status") != "completed":
            break
        if run.get("conclusion") in failures:
            streak += 1
        else:
            break
    return "OPEN" if streak >= 2 else "CLOSED"


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
    if not (MONITOR_START <= minute <= MONITOR_END):
        return "IDLE"
    breaker = circuit_state(runs, now)
    if breaker == "OPEN":
        return "CIRCUIT_OPEN"
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
    if not (MONITOR_START <= now.hour * 60 + now.minute <= MONITOR_END):
        print("IDLE: outside Amsterdam monitoring window")
        return 0
    runs = api("actions/workflows/session.yml/runs?per_page=50").get("workflow_runs", [])
    state = decision(read_status(), runs, now)
    print(f"{state}: read-only session watchdog at {now.isoformat()}")
    if state in {"ALARM", "CIRCUIT_OPEN"}:
        print("::error::AH read-only watchdog alarm; inspect session and heartbeat")
        if state == "CIRCUIT_OPEN":
            print("::error::Circuit breaker OPEN after consecutive scheduled-session failures")
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
    assert heartbeat_age_seconds(good, now) == 60
    assert heartbeat_age_seconds({}, now) is None
    failed = [
        {"event": "schedule", "status": "completed", "conclusion": "failure",
         "created_at": "2026-11-02T16:50:00Z"},
        {"event": "schedule", "status": "completed", "conclusion": "timed_out",
         "created_at": "2026-11-02T16:45:00Z"},
    ]
    assert circuit_state(failed, now) == "OPEN"
    assert decision(good, failed, now) == "CIRCUIT_OPEN"
    assert circuit_state([*failed[:1], active[0]], now) == "HALF_OPEN"
    assert decision(good, active, datetime(2026, 11, 2, 23, 0, tzinfo=TZ)) == "IDLE"
    assert not hasattr(api, "post")
    print("Read-only watchdog self-test: PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        raise SystemExit(main())
