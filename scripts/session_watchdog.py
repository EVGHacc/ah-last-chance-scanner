#!/usr/bin/env python3
"""Recover a missing/stale supervised AH session from the independent fallback workflow."""
import json
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Amsterdam")
ACTIVE=("queued","in_progress","waiting","pending","requested")
HEARTBEAT_MAX_AGE=205

def valid_heartbeat(status, now):
    if not isinstance(status,dict) or status.get("date")!=now.date().isoformat():
        return False
    if status.get("authMode")!="user-refresh" or status.get("rawExpected")!=101 or status.get("canonicalExpected")!=61:
        return False
    if status.get("category")!="Vlees":
        return False
    latest=status.get("latestValid") or {}
    if latest.get("authMode")!="user-refresh":
        return False
    try:
        checked=datetime.fromisoformat(latest["checkedAt"])
    except (KeyError,TypeError,ValueError):
        return False
    if checked.tzinfo is None:
        return False
    age=(now-checked.astimezone(TZ)).total_seconds()
    return -30 <= age <= HEARTBEAT_MAX_AGE

def active_runs(runs, now):
    today=now.astimezone(ZoneInfo("UTC")).date().isoformat()
    return [r for r in runs
            if r.get("event") in ("schedule","workflow_dispatch","push")
            and r.get("created_at","")[:10] in (today, now.date().isoformat())
            and r.get("status") in ACTIVE]

def api(path, payload=None):
    token=os.environ["GH_TOKEN"]
    repo=os.environ["GITHUB_REPOSITORY"]
    url=f"https://api.github.com/repos/{repo}/{path}"
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,headers={
        "Authorization":f"Bearer {token}","Accept":"application/vnd.github+json",
        "X-GitHub-Api-Version":"2022-11-28","User-Agent":"ah-session-watchdog",
        "Content-Type":"application/json"},method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req,timeout=15) as response:
        return json.load(response) if payload is None else response.status

def read_status():
    try:
        return json.loads(Path("data/status.json").read_text(encoding="utf-8"))
    except (OSError,ValueError):
        return {}

def main():
    now=datetime.now(TZ)
    minute=now.hour*60+now.minute
    if not (17*60+30<=minute<=22*60+10):
        print("Watchdog outside recovery window; no dispatch")
        return
    runs=api("actions/workflows/session.yml/runs?per_page=50").get("workflow_runs",[])
    active=active_runs(runs,now)
    healthy=valid_heartbeat(read_status(),now)
    # Give the primary session and the 17:32 fallback one cycle to establish
    # today's first honest heartbeat before intervening.
    if minute < 17*60+35 and not healthy:
        print("Watchdog startup grace; fallback will recover the first due point")
        return
    if healthy:
        print(f"Supervised session heartbeat healthy; active_runs={len(active)}")
        return
    # A run without a fresh valid scan is not healthy. Cancel only in-progress
    # sessions; queued redundant starters are preserved by queue:max.
    for run in active:
        if run.get("status")=="in_progress" and run.get("id"):
            try:
                code=api(f"actions/runs/{run['id']}/cancel",{})
                print(f"Cancelled stale supervised run {run['id']}: HTTP {code}")
            except Exception as exc:
                print(f"Could not cancel stale run {run['id']}: {exc}")
    code=api("actions/workflows/session.yml/dispatches",{"ref":"main"})
    print(f"Dispatched replacement supervised session after stale/missing heartbeat: HTTP {code}")

def self_test():
    n=datetime(2026,10,1,18,0,tzinfo=TZ)
    good={"date":"2026-10-01","authMode":"user-refresh","rawExpected":101,
          "canonicalExpected":61,"category":"Vlees",
          "latestValid":{"checkedAt":"2026-10-01T17:58:00+02:00","authMode":"user-refresh"}}
    stale=json.loads(json.dumps(good))
    stale["latestValid"]["checkedAt"]="2026-10-01T17:50:00+02:00"
    assert valid_heartbeat(good,n)
    assert not valid_heartbeat(stale,n)
    assert not valid_heartbeat({},n)
    assert not valid_heartbeat({**good,"category":"Vleeswaren"},n)
    runs=[{"id":1,"event":"schedule","created_at":"2026-10-01T15:55:00Z","status":"in_progress"}]
    assert len(active_runs(runs,n))==1
    print("Watchdog heartbeat/recovery self-test: PASS")

if __name__=="__main__":
    self_test() if "--self-test" in sys.argv else main()
