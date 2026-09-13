#!/usr/bin/env python3
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('persist',Path(__file__).with_name('persist.py'))
persist=importlib.util.module_from_spec(spec)
spec.loader.exec_module(persist)


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
assert persist.valid_obs(obs(raw_slot='17:33',canonical_slot='17:30',canonical_delay=190))
assert not persist.valid_obs(obs(raw_delay=241))
assert not persist.valid_obs(obs(auth='anonymous'))
assert not persist.valid_obs(obs(status='INCOMPLETE'))
assert persist.exact_canonical_obs(obs())
assert not persist.exact_canonical_obs(obs(raw_slot='17:33',canonical_slot='17:30'))
assert not persist.exact_canonical_obs(obs(canonical_delay=241))
print('scanner persistence self-test: PASS')
