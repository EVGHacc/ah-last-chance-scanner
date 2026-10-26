#!/usr/bin/env python3
"""Run from an EXTERNAL scheduler (not GitHub Actions) every 2 minutes.

Required env: GH_TOKEN (Actions:write, Contents:read), GITHUB_REPOSITORY.
Never backfills scans; it only dispatches the current supervised workflow.
"""
import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
REQUIRED_STORES = {1463, 1348, 1135}
MAX_HEARTBEAT_AGE = 240
COOLDOWN_SECONDS = 300


def decision(now, status, runs):
    minute = now.hour * 60 + now.minute
    if not (17 * 60 + 35 <= minute <= 22 * 60 + 10):
        return "outside-window"
    latest = status.get("latestValid") or {}
    try:
        checked = datetime.fromisoformat(latest["checkedAt"])
        age = (now - checked.astimezone(TZ)).total_seconds()
    except (KeyError, ValueError, TypeError):
        age = float("inf")
    healthy = (
        status.get("date") == now.date().isoformat()
        and status.get("authMode") == "user-refresh"
        and status.get("category") == "Vlees"
        and status.get("rawExpected") == 101
        and status.get("canonicalExpected") == 61
        and REQUIRED_STORES.issubset(set(status.get("stores") or []))
        and latest.get("authMode") == "user-refresh"
        and -30 <= age <= MAX_HEARTBEAT_AGE
    )
    if healthy:
        return "healthy"
    # Do not dispatch duplicates while a run is active or recently started.
    for run in runs:
        if run.get("event") not in ("workflow_dispatch", "schedule", "push"):
            continue
        try:
            created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
            elapsed = (now - created.astimezone(TZ)).total_seconds()
        except (KeyError, ValueError, TypeError):
            continue
        if elapsed < 0:
            continue
        if run.get("status") in ("queued", "in_progress", "waiting", "pending", "requested"):
            return "active-run"
        if elapsed <= COOLDOWN_SECONDS:
            return "cooldown"
    return "dispatch"


def request(path, token, repo, payload=None):
    url = f"https://api.github.com/repos/{repo}/{path}"
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST" if payload is not None else "GET",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json",
                 "User-Agent": "ah-external-recovery"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response) if payload is None else response.status


def main():
    now = datetime.now(TZ)
    if not (17 * 60 + 35 <= now.hour * 60 + now.minute <= 22 * 60 + 10):
        print("outside-window")
        return
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    # Fetch published status from GitHub, not a stale local checkout.
    file = request("contents/data/status.json?ref=main", token, repo)
    import base64
    status = json.loads(base64.b64decode(file["content"]).decode())
    runs = request("actions/workflows/session.yml/runs?per_page=15", token, repo)["workflow_runs"]
    action = decision(now, status, runs)
    print(action, now.isoformat())
    if action == "dispatch":
        code = request("actions/workflows/session.yml/dispatches", token, repo, {"ref": "main"})
        print("recovery-dispatched", code)


def self_test():
    now = datetime(2026, 10, 11, 18, 0, tzinfo=TZ)
    good = {"date": "2026-10-11", "authMode": "user-refresh", "category": "Vlees",
            "rawExpected": 101, "canonicalExpected": 61,
            "stores": [1463, 1348, 1135],
            "latestValid": {"authMode": "user-refresh", "checkedAt": "2026-10-11T17:58:00+02:00"}}
    assert decision(now, good, []) == "healthy"
    assert decision(now, {}, []) == "dispatch"
    assert decision(now, {**good, "category": "Vleeswaren"}, []) == "dispatch"
    active = [{"event": "workflow_dispatch", "created_at": "2026-10-11T15:59:00Z",
               "status": "in_progress"}]
    assert decision(now, {}, active) == "active-run"
    assert decision(now, {}, [{**active[0], "status": "completed"}]) == "cooldown"
    old_active = [{**active[0], "created_at": "2026-10-11T15:40:00Z"}]
    assert decision(now, {}, old_active) == "active-run", "never duplicate an old active session"
    assert decision(now, {}, [{**old_active[0], "status": "completed"}]) == "dispatch"
    assert decision(datetime(2026, 10, 11, 23, 0, tzinfo=TZ), {}, []) == "outside-window"
    print("external recovery tests: PASS")


if __name__ == "__main__":
    import sys
    self_test() if "--self-test" in sys.argv else main()
