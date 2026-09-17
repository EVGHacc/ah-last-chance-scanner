#!/usr/bin/env python3
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
START=17*60+30
END=22*60+30
MAX_RECOVERY_AGE=240
RETRY_DELAYS=(0,8,20)
STORES={'1463','1348','1135'}


def raw_due(minute):
    return START<=minute<=END and (minute-START)%3==0


def canonical_due(minute):
    return START<=minute<=END and (minute-START)%5==0


def due(minute):
    return raw_due(minute) or canonical_due(minute)


def points_for(date):
    return [datetime(date.year,date.month,date.day,m//60,m%60,tzinfo=TZ)
            for m in range(START,END+1) if due(m)]


def status_seen(date):
    try:
        s=json.loads(Path('data/status.json').read_text(encoding='utf-8'))
        if s.get('date') != date.strftime('%Y-%m-%d'):
            return set(),set()
        return set(s.get('rawSeen') or []),set(s.get('canonicalSeen') or [])
    except Exception:
        return set(),set()


def point_complete(target):
    raw_seen,canonical_seen=status_seen(target)
    minute=target.hour*60+target.minute
    slot=target.strftime('%H:%M')
    return ((not raw_due(minute) or slot in raw_seen) and
            (not canonical_due(minute) or slot in canonical_seen))


def refresh_checkout():
    subprocess.run(['git','fetch','origin','main'],check=False)
    subprocess.run(['git','reset','--hard','origin/main'],check=False)


def run_point(target):
    env=dict(os.environ)
    env['SCHEDULED_AT']=target.isoformat()
    for attempt,delay in enumerate(RETRY_DELAYS,1):
        if delay:
            time.sleep(delay)
        age=(datetime.now(TZ)-target).total_seconds()
        if age>MAX_RECOVERY_AGE:
            print(f'Point {target.isoformat()} no longer honestly recoverable after attempt {attempt-1}',flush=True)
            return False
        scan=subprocess.run(['python','scanner.py'],env=env)
        if scan.returncode!=0:
            print(f'Scan attempt {attempt} failed for {target.isoformat()}',flush=True)
            continue
        publish=subprocess.run(['python','scripts/publish.py'])
        if publish.returncode==0:
            refresh_checkout()
            if point_complete(target):
                return True
            print(f'Published but point still not visible in status: {target.isoformat()}',flush=True)
        else:
            print(f'Publish attempt {attempt} failed for {target.isoformat()}',flush=True)
    print(f'Point {target.isoformat()} remains missing after automatic recovery',flush=True)
    return False


def recover_recent_gaps(today):
    refresh_checkout()
    now=datetime.now(TZ)
    missing=[]
    for target in points_for(today):
        age=(now-target).total_seconds()
        if 35 <= age <= 180 and not point_complete(target):
            missing.append(target)
    for target in missing:
        print(f'Heartbeat detected missing point {target.isoformat()}; recovering now',flush=True)
        run_point(target)


def final_reconcile(today):
    refresh_checkout()
    raw_seen,canonical_seen=status_seen(today)
    expected_raw={t.strftime('%H:%M') for t in points_for(today) if raw_due(t.hour*60+t.minute)}
    expected_canonical={t.strftime('%H:%M') for t in points_for(today) if canonical_due(t.hour*60+t.minute)}
    raw_missing=sorted(expected_raw-raw_seen)
    canonical_missing=sorted(expected_canonical-canonical_seen)
    print(f'FINAL RECONCILIATION raw={len(raw_seen)}/101 canonical={len(canonical_seen)}/61',flush=True)
    if raw_missing: print('Raw missing:',','.join(raw_missing),flush=True)
    if canonical_missing: print('Canonical missing:',','.join(canonical_missing),flush=True)
    return not raw_missing and not canonical_missing and len(raw_seen)==101 and len(canonical_seen)==61


def main():
    today=datetime.now(TZ)
    points=points_for(today)
    print(f'Supervised AH session: {len(points)} intended union points, 17:30-22:30 Europe/Amsterdam',flush=True)
    for target in points:
        while True:
            delta=(target-datetime.now(TZ)).total_seconds()
            if delta<=0:
                break
            time.sleep(min(delta,30))
        recover_recent_gaps(today)
        if not point_complete(target):
            age=(datetime.now(TZ)-target).total_seconds()
            if age<=MAX_RECOVERY_AGE:
                run_point(target)
            else:
                print(f'Skipping irrecoverably late point {target.isoformat()} age={int(age)}s',flush=True)
        recover_recent_gaps(today)
    if not final_reconcile(today):
        raise SystemExit('Evening sequence incomplete after automatic recovery; see exact missing slots above')
    print('Supervised AH session finished: 101/101 raw and 61/61 canonical complete',flush=True)


if __name__=='__main__': main()
