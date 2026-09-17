#!/usr/bin/env python3
import csv,json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
CENTRAL=ROOT/'data'/'central'
CURRENT_FROM=datetime(2026,9,12).date()
TZ=ZoneInfo('Europe/Amsterdam')


def dates_between(start,end):
    while start<=end:
        yield start
        start+=timedelta(days=1)


def main():
    manifest=json.loads((CENTRAL/'metadata'/'sources.json').read_text())
    assert manifest['centralRepository']=='EVGHacc/ah-last-chance-scanner'
    hist=CENTRAL/'raw'/'historical'/'daily_counts.csv'
    assert hist.exists() and hist.stat().st_size>0
    with hist.open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
    historical=sorted({datetime.fromisoformat(r['date']).date() for r in rows})
    assert historical and historical[0]==datetime(2026,8,27).date()

    current={datetime.fromisoformat(p.stem).date():p for p in (ROOT/'data').glob('2026-*.jsonl')}
    through=datetime.now(TZ).date()-timedelta(days=1)
    missing_current=[d.isoformat() for d in dates_between(CURRENT_FROM,through) if d not in current]
    assert not missing_current, f'missing current scanner day files: {missing_current}'

    historical_end=historical[-1]
    transition_gap=[d.isoformat() for d in dates_between(historical_end+timedelta(days=1),CURRENT_FROM-timedelta(days=1))]
    print(json.dumps({'centralOk':True,'historicalFrom':historical[0].isoformat(),
                      'historicalTo':historical_end.isoformat(),'knownTransitionGap':transition_gap,
                      'currentFrom':CURRENT_FROM.isoformat(),'currentThrough':max(current).isoformat() if current else None,
                      'currentDayFiles':sorted(p.name for p in current.values())},indent=2))

if __name__=='__main__': main()
