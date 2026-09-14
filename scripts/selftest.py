#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).parent
ROOT=BASE.parent

def load(name, filename, root=BASE):
    spec=importlib.util.spec_from_file_location(name,root/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

persist=load('persist','persist.py')
watchdog=load('watchdog_targets','watchdog_targets.py')
session=load('session','session.py')
scanner=load('scanner','scanner.py',ROOT)


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

due=[m for m in range(watchdog.START,watchdog.END+1) if watchdog.raw_due(m) or watchdog.canonical_due(m)]
assert len(due)==141, len(due)

test_day=datetime(2026,9,13,12,0,tzinfo=ZoneInfo('Europe/Amsterdam'))
points=session.points_for(test_day)
assert len(points)==141, len(points)
assert points[0].strftime('%H:%M')=='17:30'
assert points[-1].strftime('%H:%M')=='22:30'
assert sum(1 for p in points if (p.hour*60+p.minute-session.START)%3==0)==101
assert sum(1 for p in points if (p.hour*60+p.minute-session.START)%5==0)==61

assert watchdog.MIN_AGE_SECONDS <= 45
assert watchdog.MAX_AGE_SECONDS <= 180
for minute in due:
    candidates=[w for w in range(minute,minute+2) if w%5 in (0,2,4)]
    assert candidates, f'watchdog has no <=1m recovery for {minute//60:02d}:{minute%60:02d}'

# First call refreshes, later calls reuse the same persisted state.
with tempfile.TemporaryDirectory() as td:
    old_state=os.environ.get('AH_TOKEN_STATE_FILE')
    old_refresh=os.environ.get('AH_REFRESH_TOKEN')
    os.environ['AH_TOKEN_STATE_FILE']=str(Path(td)/'auth.json')
    os.environ['AH_REFRESH_TOKEN']='unit-refresh'
    calls=[]
    original_post=scanner.post
    def fake_post(path,body,token=None,attempts=2):
        calls.append(path)
        return 200,{'access_token':'unit-access','expires_in':3600}
    scanner.post=fake_post
    try:
        a1,m1=scanner.token(); s1=scanner.LAST_AUTH_SOURCE
        a2,m2=scanner.token(); s2=scanner.LAST_AUTH_SOURCE
        assert a1==a2=='unit-access'
        assert m1==m2=='user-refresh'
        assert s1=='refresh' and s2=='cache', (s1,s2)
        assert calls==['/mobile-auth/v1/auth/token/refresh'], calls
        state=Path(os.environ['AH_TOKEN_STATE_FILE'])
        assert state.exists()
        assert (state.stat().st_mode & 0o777)==0o600
    finally:
        scanner.post=original_post
        if old_state is None: os.environ.pop('AH_TOKEN_STATE_FILE',None)
        else: os.environ['AH_TOKEN_STATE_FILE']=old_state
        if old_refresh is None: os.environ.pop('AH_REFRESH_TOKEN',None)
        else: os.environ['AH_REFRESH_TOKEN']=old_refresh

# The supervised session launches scanner.py as a new process for every point.
# Prove that two independent processes can reuse one valid /tmp-style state
# without any refresh secret or network call.
with tempfile.TemporaryDirectory() as td:
    state=Path(td)/'auth.json'
    state.write_text(json.dumps({'accessToken':'cross-process-access','accessExpiresAt':int(time.time())+3600,'refreshToken':''}),encoding='utf-8')
    os.chmod(state,0o600)
    env=dict(os.environ)
    env['AH_TOKEN_STATE_FILE']=str(state)
    env.pop('AH_REFRESH_TOKEN',None)
    code="import scanner; a,m=scanner.token(); assert a=='cross-process-access'; assert m=='user-refresh'; assert scanner.LAST_AUTH_SOURCE=='cache'"
    for _ in range(2):
        subprocess.run(['python','-c',code],cwd=ROOT,env=env,check=True)

print('scanner/session/persistence/watchdog/token-reuse self-test: PASS')
