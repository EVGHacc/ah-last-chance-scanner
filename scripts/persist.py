#!/usr/bin/env python3
import json
from pathlib import Path

START=17*60+30
END=22*60+30
SLOTS=[f'{m//60:02d}:{m%60:02d}' for m in range(START,END+1,5)]
RAW_SLOTS=[f'{m//60:02d}:{m%60:02d}' for m in range(START,END+1,3)]
VALID_STATUS={'OK','OK_ZERO_ROWS'}
STORE_IDS={1463,1348,1135}


def valid_obs(o):
    if not isinstance(o,dict): return False
    if o.get('authMode')!='user-refresh': return False
    if o.get('status') not in VALID_STATUS or o.get('valid') is not True: return False
    raw_delay=int(o.get('rawDelaySeconds',o.get('delaySeconds',999999)))
    if raw_delay>240: return False
    stores=o.get('stores') or []
    fetched={int(s.get('storeId')) for s in stores if s.get('fetched') is True and s.get('storeId') is not None}
    if fetched!=STORE_IDS: return False
    if 'Vlees' not in (o.get('categories') or []): return False
    return True


def exact_canonical_obs(o):
    if not valid_obs(o): return False
    slot=o.get('scheduledSlot')
    if slot not in SLOTS or o.get('rawScheduledSlot')!=slot: return False
    return int(o.get('delaySeconds',999999))<=240


def better(candidate,current):
    if current is None: return True
    c_delay=int(candidate.get('delaySeconds',999999))
    p_delay=int(current.get('delaySeconds',999999))
    if c_delay!=p_delay: return c_delay<p_delay
    return str(candidate.get('checkedAt',''))<str(current.get('checkedAt',''))


def main():
    latest_path=Path('data/latest.json')
    if not latest_path.exists(): raise SystemExit('data/latest.json ontbreekt')
    obs=json.loads(latest_path.read_text(encoding='utf-8'))
    date=obs['date']
    if not valid_obs(obs): raise SystemExit('latest observatie is niet geldig/user-refresh/3 winkels/Vlees')
    Path('data').mkdir(exist_ok=True)
    day_path=Path(f'data/{date}.jsonl')
    with day_path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(obs,ensure_ascii=False,separators=(',',':'))+'\n')

    canonical_by_slot={}
    valid_rows=[]
    raw_seen=set()
    with day_path.open(encoding='utf-8') as f:
        for line in f:
            try: o=json.loads(line)
            except Exception: continue
            if o.get('date')!=date or not valid_obs(o): continue
            valid_rows.append(o)
            raw_slot=o.get('rawScheduledSlot')
            if raw_slot:
                raw_seen.add(str(raw_slot))
            slot=o.get('scheduledSlot')
            if exact_canonical_obs(o) and better(o,canonical_by_slot.get(slot)):
                canonical_by_slot[slot]=o

    observations=[canonical_by_slot[s] for s in SLOTS if s in canonical_by_slot]
    missing=[s for s in SLOTS if s not in canonical_by_slot]
    out={
        'date':date,'expectedSlots':61,'presentSlots':len(observations),'missingSlots':missing,
        'observations':observations,
        '_source':{
            'scanner':'authenticated GitHub scanner',
            'authRequired':'user-refresh',
            'canonicalCadenceMinutes':5,
            'rawCadenceMinutes':3,
            'canonicalSelection':'exact rawScheduledSlot equals scheduledSlot; canonical delaySeconds <=240; lowest delay then earliest checkedAt'
        }
    }
    Path('data/today.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

    latest_valid=max(valid_rows,key=lambda x:str(x.get('checkedAt',''))) if valid_rows else None
    raw_expected=[s for s in RAW_SLOTS]
    raw_seen_ordered=[s for s in raw_expected if s in raw_seen]
    status={
        'date':date,
        'authMode':'user-refresh',
        'stores':[1463,1348,1135],
        'category':'Vlees',
        'rawCadenceMinutes':3,
        'canonicalCadenceMinutes':5,
        'rawExpected':len(raw_expected),
        'rawSeen':raw_seen_ordered,
        'rawMissing':[s for s in raw_expected if s not in raw_seen],
        'canonicalExpected':61,
        'canonicalSeen':[s for s in SLOTS if s in canonical_by_slot],
        'canonicalMissing':missing,
        'latestValid':None if latest_valid is None else {
            'checkedAt':latest_valid.get('checkedAt'),
            'rawScheduledAt':latest_valid.get('rawScheduledAt'),
            'rawScheduledSlot':latest_valid.get('rawScheduledSlot'),
            'scheduledSlot':latest_valid.get('scheduledSlot'),
            'status':latest_valid.get('status'),
            'authMode':latest_valid.get('authMode'),
        },
    }
    Path('data/status.json').write_text(json.dumps(status,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'persisted {date}: raw {len(raw_seen_ordered)}/{len(raw_expected)}, exact canonical {len(observations)}/61')

if __name__=='__main__': main()
