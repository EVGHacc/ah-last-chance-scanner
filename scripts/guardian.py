#!/usr/bin/env python3
"""Independent read-only observer for the AH evening scanner publication."""
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import session

TZ = ZoneInfo("Europe/Amsterdam")
OBSERVATION_DELAY_SECONDS = 55
POLL_SECONDS = 20


def wait_until(when):
    while True:
        remaining = (when - datetime.now(TZ)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(POLL_SECONDS, remaining))


def guard_point(target):
    """Observe a published slot only; never start, retry or repair a scan."""
    wait_until(target + timedelta(seconds=OBSERVATION_DELAY_SECONDS))
    if session.point_complete(target):
        print(f"GUARDIAN_HEALTHY slot={target:%H:%M}", flush=True)
        return True
    print(f"GUARDIAN_ALARM slot={target:%H:%M} missing_or_unpublished=true", flush=True)
    return False


def prestart_readiness():
    """Check local configuration only; deliberately perform no network/auth probe."""
    import os
    from production_health import validate_preflight

    validate_preflight()
    if not os.getenv("AH_REFRESH_TOKEN"):
        raise RuntimeError("PRESTART BLOCKER: AH_REFRESH_TOKEN missing; production session cannot start")
    print("PRESTART READY: refresh-token secret configured; no live-auth probe performed", flush=True)


def main():
    prestart_readiness()
    today = datetime.now(TZ)
    points = session.points_for(today)
    print("Independent AH read-only guardian active", flush=True)
    failures = []
    for target in points:
        if not guard_point(target):
            failures.append(target.strftime("%H:%M"))
    complete = session.reconcile_publication(today)
    if failures or not complete:
        print("GUARDIAN_FAILURE: missing published points=" + ",".join(failures), flush=True)
        raise SystemExit(1)
    print("GUARDIAN_COMPLETE: final reconciliation passed", flush=True)


def self_test():
    assert OBSERVATION_DELAY_SECONDS > 0
    assert callable(prestart_readiness)
    assert callable(guard_point)
    assert not hasattr(session, "fallback_once")
    assert not hasattr(session, "recover_recent_gaps")
    print("Guardian read-only observer self-test: PASS")


if __name__ == "__main__":
    self_test() if "--self-test" in sys.argv else main()
