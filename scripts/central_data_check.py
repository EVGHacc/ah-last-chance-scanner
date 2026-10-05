#!/usr/bin/env python3
import csv,json
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
CENTRAL=ROOT/'data'/'central'
CURRENT_FROM=datetime(2026,9,12).date()
LEGACY_FROM=datetime(2026,8,27).date()
TZ=ZoneInfo('Europe/Amsterdam')

def dates_between(start,end):
    while start<=end:
        yield start
        start+=timedelta(days=1)

def jsonl_quality(path):
    rows=valid=0; slots=set()
    with path.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            rows+=1
            try: o=json.loads(line)
            except Exception: continue
            if o.get('authMode')!='user-refresh' or o.get('status') not in {'OK','OK_ZERO_ROWS'} or o.get('valid') is not True: continue
            if 'Vlees' not in (o.get('categories') or []): continue
            fetched={int(s.get('storeId')) for s in o.get('stores') or [] if s.get('fetched') is True and s.get('storeId') is not None}
            if not {1463,1348,1135}.issubset(fetched): continue
            try:
                if int(o.get('rawDelaySeconds',o.get('delaySeconds',999999)))>240: continue
            except Exception: continue
            valid+=1
            if o.get('rawScheduledSlot'): slots.add(o['rawScheduledSlot'])
    return {'rows':rows,'validRows':valid,'rawSlots':len(slots),'usable':valid>0}

def build_report(now=None):
    now=now or datetime.now(TZ)
    manifest=json.loads((CENTRAL/'metadata'/'sources.json').read_text())
    assert manifest['centralRepository']=='EVGHacc/ah-last-chance-scanner'

    hist=CENTRAL/'raw'/'historical'/'daily_counts.csv'
    assert hist.exists() and hist.stat().st_size>0
    with hist.open(newline='',encoding='utf-8') as f: rows=list(csv.DictReader(f))
    historical=sorted({datetime.fromisoformat(r['date']).date() for r in rows})
    assert historical and historical[0]==LEGACY_FROM

    lifetimes=json.loads((CENTRAL/'derived'/'historical_70_lifetimes.json').read_text())
    episodes=lifetimes.get('episodes') or []
    assert episodes, 'historical product-level 70% episodes missing'
    product_dates=sorted({datetime.fromisoformat(r['date']).date() for r in episodes})
    provenance=lifetimes.get('provenance') or {}
    assert int(provenance.get('product_level_files_accepted',0))>0

    current={}
    for p in sorted((ROOT/'data').glob('2026-*.jsonl')):
        d=datetime.fromisoformat(p.stem).date()
        current[d]=jsonl_quality(p)

    through=now.date()-timedelta(days=1)
    expected=list(dates_between(CURRENT_FROM,through))
    missing=[d.isoformat() for d in expected if d not in current]
    unusable=[d.isoformat() for d in expected if d in current and not current[d]['usable']]

    hist_end=historical[-1]
    transition=[d.isoformat() for d in dates_between(hist_end+timedelta(days=1),CURRENT_FROM-timedelta(days=1))]
    return {
      'centralOk': not missing and not unusable,
      'legacyCounts':{'from':historical[0].isoformat(),'to':hist_end.isoformat(),'days':len(historical)},
      'legacyProduct70':{'from':product_dates[0].isoformat(),'to':product_dates[-1].isoformat(),'days':len(product_dates),
                         'episodes':len(episodes),'rawJsonFilesSeen':provenance.get('raw_json_files_seen'),
                         'productLevelFilesAccepted':provenance.get('product_level_files_accepted')},
      'knownTransitionGap':transition,
      'current':{'from':CURRENT_FROM.isoformat(),'through':through.isoformat(),'missingDayFiles':missing,
                 'unusableDayFiles':unusable,'days':{d.isoformat():q for d,q in sorted(current.items()) if d<=through}},
      'analysisPolicy': 'Never substitute legacy/counts data for missing current observations; compare only compatible regimes and expose coverage.'
    }

def main():
    report=build_report()
    out=CENTRAL/'derived'/'history_quality.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    assert report['centralOk'], f"current historical chain incomplete: missing={report['current']['missingDayFiles']} unusable={report['current']['unusableDayFiles']}"
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
