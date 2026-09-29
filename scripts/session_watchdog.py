#!/usr/bin/env python3
"""Start the supervised session if GitHub's scheduled start did not materialize."""
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ=ZoneInfo("Europe/Amsterdam")
def needs_dispatch(runs, now):
    today=now.date().isoformat()
    for run in runs:
        if run.get("event") not in ("schedule","workflow_dispatch","push"):
            continue
        if run.get("created_at","")[:10]!=today:
            continue
        if run.get("status") in ("queued","in_progress","waiting","pending","requested"):
            return False
    return True

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

def main():
    now=datetime.now(TZ)
    if not (17*60+30<=now.hour*60+now.minute<=22*60+10):
        print("Watchdog outside recovery window; no dispatch")
        return
    runs=api("actions/workflows/session.yml/runs?per_page=50").get("workflow_runs",[])
    if not needs_dispatch(runs,now):
        print("Supervised session already queued/running; no dispatch")
        return
    # One emergency dispatch per day, avoiding storms if the queued run fails.
    if any(x.get("event")=="workflow_dispatch" and x.get("created_at","")[:10]==now.date().isoformat() for x in runs):
        print("Emergency dispatch already attempted today")
        return
    status=api("actions/workflows/session.yml/dispatches",{"ref":"main"})
    print(f"Emergency supervised session dispatched: HTTP {status}")

def self_test():
    n=datetime(2026,9,29,17,32,tzinfo=TZ)
    assert needs_dispatch([],n)
    assert not needs_dispatch([{"event":"schedule","created_at":"2026-09-29T15:00:00Z","status":"queued"}],n)
    assert not needs_dispatch([{"event":"workflow_dispatch","created_at":"2026-09-29T15:00:00Z","status":"in_progress"}],n)
    assert needs_dispatch([{"event":"schedule","created_at":"2026-09-28T15:00:00Z","status":"in_progress"}],n)
    print("Watchdog self-test: PASS")

if __name__=="__main__":
    self_test() if "--self-test" in sys.argv else main()
