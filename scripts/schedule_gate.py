#!/usr/bin/env python3
"""Fail-closed gate for the 17:25 Europe/Amsterdam AH prestart."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
PRESTART_HOUR = 17
PRESTART_MINUTE = 25
MAX_START_DELAY_SECONDS = 240


def allowed(event, schedule, now):
    """Admit only the intended DST-aware cron event within four minutes."""
    if event != "schedule" or not isinstance(now, datetime) or now.tzinfo is None:
        return False
    local_now = now.astimezone(TZ)
    target = datetime(
        local_now.year,
        local_now.month,
        local_now.day,
        PRESTART_HOUR,
        PRESTART_MINUTE,
        tzinfo=TZ,
    )
    delay = (local_now - target).total_seconds()
    if not 0 <= delay <= MAX_START_DELAY_SECONDS:
        return False
    utc_hour = PRESTART_HOUR - int(target.utcoffset().total_seconds() // 3600)
    expected_schedule = f"{PRESTART_MINUTE} {utc_hour} * * *"
    return schedule == expected_schedule


def self_test():
    summer = datetime(2026, 7, 10, 17, 25, tzinfo=TZ)
    winter = datetime(2026, 11, 2, 17, 25, tzinfo=TZ)
    assert allowed("schedule", "25 15 * * *", summer)
    assert allowed("schedule", "25 16 * * *", winter)
    assert allowed("schedule", "25 16 * * *", winter.replace(minute=29))
    assert not allowed("schedule", "25 16 * * *", winter.replace(minute=29, second=1))
    assert not allowed("schedule", "30 16 * * *", winter)
    assert not allowed("workflow_dispatch", "", winter)
    assert not allowed("push", "", winter)
    assert not allowed("schedule", "25 16 * * *", winter.replace(minute=24, second=59))
    assert not allowed("schedule", "25 16 * * *", winter.replace(minute=30))
    print("AH prestart schedule gate tests: PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        now = datetime.now(TZ)
        event = os.getenv("EVENT_NAME", "")
        schedule = os.getenv("EVENT_SCHEDULE", "")
        run = allowed(event, schedule, now)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"run={str(run).lower()}\n")
        print("Amsterdam=", now.isoformat(), "event=", event, "schedule=", schedule, "run=", run)
