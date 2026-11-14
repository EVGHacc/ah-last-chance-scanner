#!/usr/bin/env python3
"""Fail-closed gate for the single DST-adjusted Amsterdam prestart event."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
PRESTART_MINUTES = (17 * 60 + 25, 17 * 60 + 28)
MAX_START_DELAY_SECONDS = 240
CONFIGURED_CRONS = {"25 15 * * *", "25 16 * * *", "28 15 * * *", "28 16 * * *"}


def _cron_for(target):
    utc_hour = target.hour - int(target.utcoffset().total_seconds() // 3600)
    return f"{target.minute} {utc_hour} * * *"


def classify(event, schedule, now, claimed=False):
    """Distinguish an intentionally inactive DST cron from a missed live prestart."""
    if not isinstance(now, datetime) or now.tzinfo is None or event != "schedule":
        return "reject"
    if schedule not in CONFIGURED_CRONS:
        return "reject"
    local_now = now.astimezone(TZ)
    targets = [
        datetime(local_now.year, local_now.month, local_now.day,
                 minute // 60, minute % 60, tzinfo=TZ)
        for minute in PRESTART_MINUTES
    ]
    matching = [target for target in targets if schedule == _cron_for(target)]
    if not matching:
        return "inactive"
    target = matching[0]
    if claimed:
        return "claimed"
    delay = (local_now - target).total_seconds()
    if delay < 0:
        return "early"
    if delay > MAX_START_DELAY_SECONDS:
        return "late"
    return "run"


def allowed(event, schedule, now, **_ignored):
    """Compatibility helper retained for existing callers and tests."""
    return classify(event, schedule, now) == "run"


def self_test():
    summer_primary = datetime(2026, 7, 10, 17, 25, tzinfo=TZ)
    winter_primary = datetime(2026, 11, 2, 17, 25, tzinfo=TZ)
    assert classify("schedule", "25 15 * * *", summer_primary) == "run"
    assert classify("schedule", "25 16 * * *", winter_primary) == "run"
    assert classify("schedule", "28 15 * * *", summer_primary.replace(minute=28)) == "run"
    assert classify("schedule", "28 16 * * *", winter_primary.replace(minute=28)) == "run"
    assert classify("schedule", "28 16 * * *", winter_primary.replace(minute=28), claimed=True) == "claimed"
    assert classify("schedule", "25 15 * * *", winter_primary) == "inactive"
    assert classify("schedule", "25 16 * * *", summer_primary) == "inactive"
    assert classify("schedule", "25 16 * * *", winter_primary.replace(minute=29)) == "run"
    assert classify("schedule", "25 16 * * *", winter_primary.replace(minute=29, second=1)) == "late"
    assert classify("schedule", "28 16 * * *", winter_primary.replace(minute=32, second=1)) == "late"
    assert classify("schedule", "30 16 * * *", winter_primary) == "reject"
    assert classify("push", "", winter_primary) == "reject"
    print("AH schedule gate tests: PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        now = datetime.now(TZ)
        decision = classify(
            os.getenv("EVENT_NAME", ""),
            os.getenv("EVENT_SCHEDULE", ""),
            now,
            claimed=__import__("pathlib").Path(".state/ah-session-claims", now.strftime("%Y-%m-%d") + ".lock").exists(),
        )
        run = decision == "run"
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"run={str(run).lower()}\n")
            output.write(f"decision={decision}\n")
        print("Amsterdam=", now.isoformat(), "event=", os.getenv("EVENT_NAME", ""),
              "schedule=", os.getenv("EVENT_SCHEDULE", ""), "decision=", decision)
