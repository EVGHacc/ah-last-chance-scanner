#!/usr/bin/env python3
"""Independent long-running production guardian for the AH evening scanner.

The guardian does not trust GitHub run state. It watches the authoritative
published slot data and takes over a missing point while it is still honestly
recoverable inside the <=240 second validity limit.
"""
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import session

TZ=ZoneInfo("Europe/Amsterdam")
CHECK_AFTER_SECONDS=55
SECOND_CHECK_SECONDS=20
POLL_SECONDS=20


def takeover_due(target, now):
    age=(now-target).total_seconds()
    return CHECK_AFTER_SECONDS <= age <= session.RECOVERY_START_DEADLINE


def wait_until(when):
    while True:
        remaining=(when-datetime.now(TZ)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(POLL_SECONDS,remaining))


def guard_point(target):
    # First check after 55s: enough time for primary publish, but >3 minutes
    # remain before the hard 240s validity boundary.
    wait_until(target+timedelta(seconds=CHECK_AFTER_SECONDS))
    session.refresh_checkout()
    if session.point_complete(target):
        print(f"Guardian healthy {target:%H:%M}: primary output present",flush=True)
        return True

    # Avoid racing a primary publication that is merely a few seconds late.
    time.sleep(SECOND_CHECK_SECONDS)
    session.refresh_checkout()
    if session.point_complete(target):
        print(f"Guardian healthy after double-check {target:%H:%M}",flush=True)
        return True

    now=datetime.now(TZ)
    if not takeover_due(target,now):
        print(f"Guardian cannot honestly recover {target:%H:%M}; age={(now-target).total_seconds():.0f}s",flush=True)
        return False

    print(f"SELF-HEAL takeover for missing production point {target.isoformat()}",flush=True)
    return session.run_point(target)


def main():
    today=datetime.now(TZ)
    points=session.points_for(today)
    print("Independent AH guardian active; monitoring authoritative production slots",flush=True)
    for target in points:
        # A delayed guardian can still save only recent points; never backdate.
        age=(datetime.now(TZ)-target).total_seconds()
        if age > session.RECOVERY_START_DEADLINE:
            continue
        guard_point(target)
    session.final_reconcile(today)


def self_test():
    t=datetime(2026,10,2,17,30,tzinfo=TZ)
    assert not takeover_due(t,t+timedelta(seconds=54))
    assert takeover_due(t,t+timedelta(seconds=55))
    assert takeover_due(t,t+timedelta(seconds=session.RECOVERY_START_DEADLINE))
    assert not takeover_due(t,t+timedelta(seconds=session.RECOVERY_START_DEADLINE+1))
    # 55s + 20s double-check leaves 130s before recovery-start deadline.
    assert CHECK_AFTER_SECONDS+SECOND_CHECK_SECONDS < session.RECOVERY_START_DEADLINE
    assert session.MAX_RECOVERY_AGE==240
    print("Guardian failover timing self-test: PASS")


if __name__=="__main__":
    self_test() if "--self-test" in sys.argv else main()
