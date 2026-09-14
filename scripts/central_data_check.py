#!/usr/bin/env python3
import csv, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CENTRAL=ROOT/'data'/'central'


def main():
    manifest=json.loads((CENTRAL/'metadata'/'sources.json').read_text())
    assert manifest['centralRepository']=='EVGHacc/ah-last-chance-scanner'
    hist=CENTRAL/'raw'/'historical'/'daily_counts.csv'
    assert hist.exists() and hist.stat().st_size>0
    with hist.open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    dates=sorted({r['date'] for r in rows})
    assert dates and dates[0]=='2026-08-27'
    current=sorted((ROOT/'data').glob('2026-*.jsonl'))
    print(json.dumps({
        'centralOk': True,
        'historicalDailyCountsRows': len(rows),
        'historicalFrom': dates[0],
        'historicalTo': dates[-1],
        'currentDayFiles': [p.name for p in current],
        'sourceCount': len(manifest['sources'])
    },ensure_ascii=False,indent=2))

if __name__=='__main__': main()
