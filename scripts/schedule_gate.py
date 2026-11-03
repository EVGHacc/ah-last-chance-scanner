#!/usr/bin/env python3
"""Fail-closed gate for the primary and redundant Amsterdam prestart events."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
PRESTART_MINUTES = (17 * 60 + 25, 17 * 60 + 28)
MAX_START_DELAY_SECONDS = 240


def _cron_for(target):
    utc_hour = target.hour - int(target.utcoffset().total_seconds() // 3600)
    return f"{target.minute} {utc_hour} * * *"


def allowed(event, schedule, now):
    """Admit only an exact DST-aware prestart cron, within four minutes of it."""
    if event != "schedule" or not isinstance(now, datetime) or now.tzinfo is None:
        return False

    local_now = now.astimezone(TZ)
    for minute_of_day in PRESTART_MINUTES:
        target = datetime(
            local_now.year,
            local_now.month,
            local_now.day,
            minute_of_day // 60,
            minute_of_day % 60,
            tzinfo=TZ,
        )
        delay = (local_now - target).total_seconds()
        if schedule == _cron_for(target) and 0 <= delay <= MAX_START_DELAY_SECONDS:
            return True
    return False


def self_test():
    summer_primary = datetime(2026, 7, 10, 17, 25, tzinfo=TZ)
    winter_primary = datetime(2026, 11, 2, 17, 25, tzinfo=TZ)
    summer_backup = datetime(2026, 7, 10, 17, 28, tzinfo=TZ)
    winter_backup = datetime(2026, 11, 2, 17, 28, tzinfo=TZ)

    assert allowed("schedule", "25 15 * * *", summer_primary)
    assert allowed("schedule", "25 16 * * *", winter_primary)
    assert allowed("schedule", "28 15 * * *", summer_backup)
    assert allowed("schedule", "28 16 * * *", winter_backup)
    assert allowed("schedule", "28 16 * * *", winter_backup.replace(minute=32))
    assert not allowed("schedule", "28 16 * * *", winter_backup.replace(minute=32, second=1))
    assert not allowed("schedule", "25 16 * * *", winter_primary.replace(minute=29, second=1))
    assert not allowed("schedule", "30 16 * * *", winter_primary)
    assert not allowed("workflow_dispatch", "", winter_primary)
    assert not allowed("push", "", winter_primary)
    assert not allowed("schedule", "25 16 * * *", winter_primary.replace(minute=24, second=59))
    assert not allowed("schedule", "28 16 * * *", winter_backup.replace(minute=27, second=59))
    print("AH primary/redundant prestart schedule gate tests: PASS")


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
