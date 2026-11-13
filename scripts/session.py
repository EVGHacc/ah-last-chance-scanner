#!/usr/bin/env python3
import json
import sys
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
START=17*60+30
END=22*60+30
MAX_SLOT_DELAY_SECONDS=240
STORES={'1463','1348','1135','4046','8728'}


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
    """Refresh the authoritative main checkout or fail closed without logging stderr."""
    commands = (
        ("fetch", ["git", "fetch", "origin", "main"]),
        ("reset", ["git", "reset", "--hard", "origin/main"]),
    )
    for stage, command in commands:
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"CHECKOUT_REFRESH_FAILED stage={stage} exit={result.returncode}; "
                "stderr_suppressed=true"
            )


def run_point(target):
    """Run exactly one on-time observation; never retry or recover a missed slot."""
    age=(datetime.now(TZ)-target).total_seconds()
    if age < 0 or age > MAX_SLOT_DELAY_SECONDS:
        print(f"SKIPPED invalid/late slot={target:%H:%M} age={int(age)}s",flush=True)
        return False
    env=dict(os.environ)
    env["SCHEDULED_AT"]=target.isoformat()
    scan=subprocess.run(["python","scanner.py"],env=env,text=True,capture_output=True)
    try:
        obs=json.loads(Path("data/latest.json").read_text(encoding="utf-8"))
    except (ValueError,OSError):
        obs={}
    stores=obs.get("stores") or []
    summary=(f"slot={target:%H:%M} status={obs.get('status','unknown')} "
             f"auth={obs.get('authMode','unknown')} "
             f"fetched={sum(s.get('fetched') is True for s in stores)}/5")
    if scan.returncode != 0:
        print(f"SCAN_FAILURE {summary} exit={scan.returncode}; stderr_suppressed=true",flush=True)
        return False
    publish=subprocess.run(["python","scripts/publish.py"],capture_output=True,text=True)
    if publish.returncode != 0:
        print(f"PUBLISH_FAILURE {summary} exit={publish.returncode}; stderr_suppressed=true",flush=True)
        return False
    refresh_checkout()
    if not point_complete(target):
        print(f"PUBLICATION_NOT_VERIFIED slot={target:%H:%M}",flush=True)
        return False
    print(f"SCAN_AND_PUBLICATION_VERIFIED {summary}",flush=True)
    return True


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


def self_test():
    d=datetime(2026,10,1,17,30,tzinfo=TZ)
    pts=points_for(d)
    raw=[p for p in pts if raw_due(p.hour*60+p.minute)]
    canonical=[p for p in pts if canonical_due(p.hour*60+p.minute)]
    assert len(raw)==101 and raw[0].strftime('%H:%M')=='17:30' and raw[-1].strftime('%H:%M')=='22:30'
    assert len(canonical)==61 and canonical[0].strftime('%H:%M')=='17:30' and canonical[-1].strftime('%H:%M')=='22:30'
    assert MAX_SLOT_DELAY_SECONDS==240
    assert STORES=={'1463','1348','1135','4046','8728'}
    print('Session cadence self-test: PASS')


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
        # Never scan using a stale checkout or continue after a failed refresh.
        refresh_checkout()
        if not point_complete(target):
            age=(datetime.now(TZ)-target).total_seconds()
            if age<=MAX_SLOT_DELAY_SECONDS:
                run_point(target)
            else:
                print(f'Skipping expired slot {target.isoformat()} age={int(age)}s',flush=True)
    if not final_reconcile(today):
        raise SystemExit('Evening sequence incomplete; no automatic recovery was attempted')
    print('Supervised AH session finished: 101/101 raw and 61/61 canonical complete',flush=True)


if __name__=='__main__':
    if '--self-test' in sys.argv:
        self_test()
    else:
        main()
