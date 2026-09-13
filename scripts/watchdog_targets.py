#!/usr/bin/env python3
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Amsterdam')
START = 17 * 60 + 30
END = 22 * 60 + 30
MIN_AGE_SECONDS = 45
MAX_AGE_SECONDS = 195


def raw_due(minute_of_day: int) -> bool:
    return START <= minute_of_day <= END and (minute_of_day - START) % 3 == 0


def canonical_due(minute_of_day: int) -> bool:
    return START <= minute_of_day <= END and (minute_of_day - START) % 5 == 0


def load_seen(date: str):
    raw_seen, canonical_seen = set(), set()
    try:
        status = json.loads(Path('data/status.json').read_text(encoding='utf-8'))
        if status.get('date') == date:
            raw_seen = set(status.get('rawSeen') or [])
            canonical_seen = set(status.get('canonicalSeen') or [])
    except Exception:
        pass
    return raw_seen, canonical_seen


def main():
    now = datetime.now(TZ)
    date = now.strftime('%Y-%m-%d')
    raw_seen, canonical_seen = load_seen(date)
    targets = []

    for minute in range(START, END + 1):
        if not (raw_due(minute) or canonical_due(minute)):
            continue
        target = now.replace(hour=minute // 60, minute=minute % 60, second=0, microsecond=0)
        age = (now - target).total_seconds()
        if age < MIN_AGE_SECONDS or age > MAX_AGE_SECONDS:
            continue
        slot = target.strftime('%H:%M')
        complete = ((not raw_due(minute) or slot in raw_seen) and
                    (not canonical_due(minute) or slot in canonical_seen))
        if not complete:
            targets.append(target.isoformat())

    # Oldest first: this preserves the most time-sensitive still-honest recovery point.
    for target in targets:
        print(target)


if __name__ == '__main__':
    main()
