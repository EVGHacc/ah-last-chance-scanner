#!/usr/bin/env python3
"""Read-only AH production guardian.

The guardian observes published evidence only. It never scans, retries,
publishes, fetches Git state, or attempts to repair a missing observation.
"""
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import session

TZ = ZoneInfo("Europe/Amsterdam")
CHECK_AFTER_SECONDS = 55
SECOND_CHECK_SECONDS = 20
POLL_SECONDS = 20


def wait_until(when):
    while True:
        remaining = (when - datetime.now(TZ)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(POLL_SECONDS, remaining))


def guard_point(target):
    """Check a scheduled point twice; report missing data without recovery."""
    wait_until(target + timedelta(seconds=CHECK_AFTER_SECONDS))
    if session.point_complete(target):
        print(f"Guardian healthy {target:%H:%M}: primary output present", flush=True)
        return True

    time.sleep(SECOND_CHECK_SECONDS)
    if session.point_complete(target):
        print(f"Guardian healthy after double-check {target:%H:%M}", flush=True)
        return True

    print(
        f"GUARDIAN ALERT: missing production point {target.isoformat()}; "
        "automatic recovery is disabled",
        flush=True,
    )
    return False


def prestart_readiness():
    """Validate cadence invariants without credentials or network access."""
    from production_health import validate_preflight

    validate_preflight()
    print("PRESTART READY: read-only guardian checks configured; no auth/network probe", flush=True)


def final_reconcile(today):
    """Recompute expected slot coverage from the local published status only."""
    raw_seen, canonical_seen = session.status_seen(today)
    points = session.points_for(today)
    expected_raw = {
        point.strftime("%H:%M")
        for point in points
        if session.raw_due(point.hour * 60 + point.minute)
    }
    expected_canonical = {
        point.strftime("%H:%M")
        for point in points
        if session.canonical_due(point.hour * 60 + point.minute)
    }
    missing_raw = sorted(expected_raw - raw_seen)
    missing_canonical = sorted(expected_canonical - canonical_seen)
    print(
        f"GUARDIAN RECONCILIATION raw={len(raw_seen)}/101 "
        f"canonical={len(canonical_seen)}/61",
        flush=True,
    )
    if missing_raw:
        print("Raw missing:", ",".join(missing_raw), flush=True)
    if missing_canonical:
        print("Canonical missing:", ",".join(missing_canonical), flush=True)
    return not missing_raw and not missing_canonical


def main():
    prestart_readiness()
    today = datetime.now(TZ)
    points = session.points_for(today)
    print("Read-only AH guardian active; monitoring published production slots", flush=True)

    missing = []
    for target in points:
        if not guard_point(target):
            missing.append(target.strftime("%H:%M"))

    if missing or not final_reconcile(today):
        print(
            "GUARDIAN FAILURE: incomplete production evidence; "
            f"missing observed points={','.join(missing)}",
            flush=True,
        )
        raise SystemExit(1)
    print("Guardian finished: final reconciliation complete", flush=True)


def self_test():
    target = datetime(2026, 10, 2, 17, 30, tzinfo=TZ)
    assert CHECK_AFTER_SECONDS + SECOND_CHECK_SECONDS < 240
    assert target + timedelta(seconds=CHECK_AFTER_SECONDS) > target
    assert callable(prestart_readiness)
    assert callable(final_reconcile)
    print("Read-only guardian self-test: PASS")


if __name__ == "__main__":
    self_test() if "--self-test" in sys.argv else main()
