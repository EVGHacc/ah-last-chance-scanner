#!/usr/bin/env python3
import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).parent

def load(name, filename):
    spec=importlib.util.spec_from_file_location(name,BASE/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

persist=load('persist','persist.py')
watchdog=load('watchdog_targets','watchdog_targets.py')
session=load('session','session.py')


def store(store_id):
    return {'storeId':store_id,'fetched':True}


def obs(raw_slot='17:30',canonical_slot='17:30',raw_delay=10,canonical_delay=10,auth='user-refresh',status='OK',valid=True):
    return {
        'date':'2026-09-13','scheduledSlot':canonical_slot,'rawScheduledSlot':raw_slot,
        'rawDelaySeconds':raw_delay,'delaySeconds':canonical_delay,'authMode':auth,
        'status':status,'valid':valid,'categories':['Vlees','Bakkerij'],
        'stores':[store(1463),store(1348),store(1135)],'checkedAt':'2026-09-13T17:30:10+02:00'
    }

assert len(persist.RAW_SLOTS)==101, len(persist.RAW_SLOTS)
assert persist.RAW_SLOTS[0]=='17:30' and persist.RAW_SLOTS[-1]=='22:30'
assert len(persist.SLOTS)==61, len(persist.SLOTS)
assert persist.SLOTS[0]=='17:30' and persist.SLOTS[-1]=='22:30'
assert persist.valid_obs(obs())
assert not persist.valid_obs(obs(raw_delay=241))
assert not persist.valid_obs(obs(auth='anonymous'))
assert not persist.valid_obs(obs(status='INCOMPLETE'))
assert persist.exact_canonical_obs(obs())
assert not persist.exact_canonical_obs(obs(raw_slot='17:33',canonical_slot='17:30'))
assert not persist.exact_canonical_obs(obs(canonical_delay=241))

# Every intended point must be either raw 3-minute, exact canonical 5-minute, or both.
due=[m for m in range(watchdog.START,watchdog.END+1) if watchdog.raw_due(m) or watchdog.canonical_due(m)]
assert len(due)==141, len(due)

# The supervised session must cover the same 141-point union, including both endpoints.
test_day=datetime(2026,9,13,12,0,tzinfo=ZoneInfo('Europe/Amsterdam'))
points=session.points_for(test_day)
assert len(points)==141, len(points)
assert points[0].strftime('%H:%M')=='17:30'
assert points[-1].strftime('%H:%M')=='22:30'
assert sum(1 for p in points if (p.hour*60+p.minute-session.START)%3==0)==101
assert sum(1 for p in points if (p.hour*60+p.minute-session.START)%5==0)==61

# The two watchdog cron offsets (minute % 5 == 0 or 2) reach every intended point
# no later than two minutes afterward, leaving room inside the 240s validity budget.
for minute in due:
    candidates=[w for w in range(minute,minute+3) if w%5 in (0,2)]
    assert candidates, f'watchdog has no <=2m recovery for {minute//60:02d}:{minute%60:02d}'

print('scanner/session/persistence/watchdog self-test: PASS')
