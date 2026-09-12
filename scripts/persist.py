#!/usr/bin/env python3
import json
from pathlib import Path

START=17*60+30
END=22*60+30
SLOTS=[f'{m//60:02d}:{m%60:02d}' for m in range(START,END+1,5)]
VALID_STATUS={'OK','OK_ZERO_ROWS'}
STORE_IDS={1463,1348,1135}


def valid_obs(o):
    if not isinstance(o,dict): return False
    if o.get('authMode')!='user-refresh': return False
    if o.get('status') not in VALID_STATUS or o.get('valid') is not True: return False
    if int(o.get('delaySeconds',999999))>240: return False
    stores=o.get('stores') or []
    fetched={int(s.get('storeId')) for s in stores if s.get('fetched') is True and s.get('storeId') is not None}
    if fetched!=STORE_IDS: return False
    if 'Vlees' not in (o.get('categories') or []): return False
    return True


def better(candidate, current):
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

    by_slot={}
    with day_path.open(encoding='utf-8') as f:
        for line in f:
            try: o=json.loads(line)
            except Exception: continue
            slot=o.get('scheduledSlot')
            if o.get('date')==date and slot in SLOTS and valid_obs(o) and better(o,by_slot.get(slot)):
                by_slot[slot]=o
    observations=[by_slot[s] for s in SLOTS if s in by_slot]
    missing=[s for s in SLOTS if s not in by_slot]
    out={
        'date':date,'expectedSlots':61,'presentSlots':len(observations),'missingSlots':missing,
        'observations':observations,
        '_source':{
            'scanner':'authenticated GitHub scanner',
            'authRequired':'user-refresh',
            'canonicalCadenceMinutes':5,
            'rawCadenceMinutes':3,
            'canonicalSelection':'lowest delaySeconds, then earliest checkedAt'
        }
    }
    Path('data/today.json').write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(f'persisted {date}: canonical {len(observations)}/61')

if __name__=='__main__': main()
