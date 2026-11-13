#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

START=17*60+30
END=22*60+30
SLOTS=[f'{m//60:02d}:{m%60:02d}' for m in range(START,END+1,5)]
RAW_SLOTS=[f'{m//60:02d}:{m%60:02d}' for m in range(START,END+1,3)]
VALID_STATUS={'OK','OK_ZERO_ROWS'}
REQUIRED_STORE_IDS={1463,1348,1135,4046,8728}
TZ=ZoneInfo('Europe/Amsterdam')


def valid_obs(o):
    if not isinstance(o,dict) or o.get('authMode')!='user-refresh': return False
    if o.get('status') not in VALID_STATUS or o.get('valid') is not True: return False
    slot=o.get('rawScheduledSlot')
    if slot not in RAW_SLOTS + SLOTS or o.get('scheduledSlot') != slot: return False
    if o.get('scheduledAt') != o.get('rawScheduledAt'): return False
    try:
        target=datetime.fromisoformat(o['rawScheduledAt'])
        started=datetime.fromisoformat(o['startedAt'])
        checked=datetime.fromisoformat(o['checkedAt'])
        raw_delay=int(o.get('rawDelaySeconds',999999))
        delay=int(o.get('delaySeconds',999999))
        stores=o.get('stores') or []
        fetched={int(store.get('storeId')) for store in stores
                 if isinstance(store,dict) and store.get('fetched') is True
                 and store.get('storeId') is not None}
    except (KeyError,TypeError,ValueError,AttributeError):
        return False
    elapsed=(started-target).total_seconds()
    if (target.tzinfo is None or started.tzinfo is None or checked.tzinfo is None
            or target.date().isoformat()!=o.get('date')
            or target.strftime('%H:%M')!=slot
            or target.utcoffset()!=target.astimezone(TZ).utcoffset()
            or started.date()!=target.date() or checked.date()!=target.date()
            or not 0<=raw_delay<=240 or not 0<=delay<=240
            or abs(elapsed-raw_delay)>2 or abs(elapsed-delay)>2
            or started>checked):
        return False
    return (len(stores)==len(REQUIRED_STORE_IDS) and fetched==REQUIRED_STORE_IDS
            and o.get('categories')==['Vlees'])


def exact_canonical_obs(o):
    slot=o.get('scheduledSlot')
    return valid_obs(o) and slot in SLOTS and o.get('rawScheduledSlot')==slot and int(o.get('delaySeconds',999999))<=240


def better(candidate,current):
    if current is None: return True
    a=(int(candidate.get('delaySeconds',999999)),str(candidate.get('checkedAt','')))
    b=(int(current.get('delaySeconds',999999)),str(current.get('checkedAt','')))
    return a<b


def compact_obs(o):
    keep=('schemaVersion','date','weekday','scheduledSlot','scheduledAt','rawScheduledSlot','rawScheduledAt',
          'checkedAt','delaySeconds','rawDelaySeconds','status','valid','official1925','authMode')
    c={k:o.get(k) for k in keep if k in o}; c['categories']=['Vlees']; c['stores']=[]
    for s in o.get('stores') or []:
        cs={k:s.get(k) for k in ('storeId','store','fetched','meatItems','meat70Items','meat70Stock','all70Items','all70Stock') if k in s}
        cs['all70']=[{k:i.get(k) for k in ('productId','title','brand','size','category','discountPct','stock','priceWas','priceNow','markdownExpirationDate') if k in i}
                     for i in (s.get('all70') or []) if float(i.get('discountPct',0) or 0)>=70]
        cs['items']=[{k:i.get(k) for k in ('productId','title','brand','size','category','discountPct','stock','priceWas','priceNow','markdownExpirationDate') if k in i}
                     for i in (s.get('items') or []) if i.get('category')=='Vlees']
        c['stores'].append(cs)
    return c


def main():
    latest=Path('data/latest.json')
    if not latest.exists(): raise SystemExit('data/latest.json ontbreekt')
    obs=json.loads(latest.read_text(encoding='utf-8')); date=obs['date']
    if not valid_obs(obs): raise SystemExit('latest observatie is niet geldig/user-refresh/5 winkels/Vlees')

    slot=obs.get('rawScheduledSlot') or obs.get('scheduledSlot')
    if slot not in RAW_SLOTS + SLOTS or obs.get('scheduledSlot') != slot:
        raise SystemExit('latest observatie heeft een ongeldig meetpunt')
    day=Path(f'data/{date}.jsonl'); day.parent.mkdir(exist_ok=True)
    row_text=json.dumps(obs,ensure_ascii=False,separators=(',',':'))
    slot_dir=Path('data/raw')/date
    slot_dir.mkdir(parents=True,exist_ok=True)
    slot_file=slot_dir/f"{slot.replace(':','')}.json"

    existing_raw=None
    if slot_file.exists():
        try:
            existing_raw=json.loads(slot_file.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            raise SystemExit(f'onleesbaar immutable raw-slotbestand: {slot}')
        if existing_raw != obs:
            raise SystemExit(f'weigert bestaande historische slotmeting te overschrijven: {slot}')

    existing_rows=[]
    if day.exists():
        with day.open(encoding='utf-8') as source:
            for line in source:
                if not line.strip(): continue
                try:
                    previous=json.loads(line)
                except ValueError:
                    raise SystemExit('weigert JSONL met ongeldige historische regel te wijzigen')
                if previous.get('date')==date and previous.get('rawScheduledSlot')==slot:
                    existing_rows.append(previous)
    if existing_rows and (len(existing_rows)!=1 or existing_rows[0] != obs):
        raise SystemExit(f'weigert dubbele of afwijkende JSONL-slotmeting: {slot}')

    if existing_raw is None:
        slot_file.write_text(row_text,encoding='utf-8')
    if not existing_rows:
        with day.open('a',encoding='utf-8') as f:
            f.write(row_text+'\n')

    # Durable per-observation archive remains immutable; identical replays are idempotent.

    canonical={}; valid_rows=[]; raw_seen=set()
    with day.open(encoding='utf-8') as f:
        for line in f:
            try: o=json.loads(line)
            except Exception: continue
            if o.get('date')!=date or not valid_obs(o): continue
            valid_rows.append(o)
            if o.get('rawScheduledSlot') in RAW_SLOTS: raw_seen.add(o['rawScheduledSlot'])
            slot=o.get('scheduledSlot')
            if exact_canonical_obs(o) and better(o,canonical.get(slot)): canonical[slot]=o

    observations=[compact_obs(canonical[s]) for s in SLOTS if s in canonical]
    missing=[s for s in SLOTS if s not in canonical]
    today={'date':date,'expectedSlots':61,'presentSlots':len(observations),'missingSlots':missing,'observations':observations,
           '_source':{'scanner':'authenticated GitHub scanner','authRequired':'user-refresh','canonicalCadenceMinutes':5,
                      'rawCadenceMinutes':3,'scope':'canonical Vlees view; lossless raw observations remain in data/YYYY-MM-DD.jsonl and data/raw/YYYY-MM-DD/HHMM.json',
                      'canonicalSelection':'exact rawScheduledSlot equals scheduledSlot; canonical delaySeconds <=240; lowest delay then earliest checkedAt'}}
    Path('data/today.json').write_text(json.dumps(today,ensure_ascii=False,separators=(',',':')),encoding='utf-8')

    latest_valid=max(valid_rows,key=lambda x:str(x.get('checkedAt',''))) if valid_rows else None
    raw_seen_ordered=[s for s in RAW_SLOTS if s in raw_seen]
    status={'date':date,'authMode':'user-refresh','stores':[1463,1348,1135,4046,8728],'category':'Vlees',
            'rawCadenceMinutes':3,'canonicalCadenceMinutes':5,'rawExpected':101,'rawSeen':raw_seen_ordered,
            'rawMissing':[s for s in RAW_SLOTS if s not in raw_seen],'canonicalExpected':61,
            'canonicalSeen':[s for s in SLOTS if s in canonical],'canonicalMissing':missing,
            'latestValid':None if latest_valid is None else {k:latest_valid.get(k) for k in ('checkedAt','rawScheduledAt','rawScheduledSlot','scheduledSlot','status','authMode')}}
    status_text=json.dumps(status,ensure_ascii=False,separators=(',',':'))
    Path('data/status.json').write_text(status_text,encoding='utf-8')
    archive=Path('data/days')/f'{date}.status.json'; archive.parent.mkdir(exist_ok=True)
    archive.write_text(status_text,encoding='utf-8')
    print(f'persisted {date}: raw {len(raw_seen_ordered)}/101, exact canonical {len(observations)}/61')

if __name__=='__main__': main()
