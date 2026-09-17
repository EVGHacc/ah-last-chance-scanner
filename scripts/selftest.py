#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE=Path(__file__).parent
ROOT=BASE.parent
sys.path.insert(0,str(ROOT)) if str(ROOT) not in sys.path else None


def load(name,filename,root=BASE):
    spec=importlib.util.spec_from_file_location(name,root/filename)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

persist=load('persist','persist.py')
session=load('session','session.py')
scanner=load('scanner','scanner.py',ROOT)
auth_state=load('auth_state','auth_state.py')


def store(store_id): return {'storeId':store_id,'fetched':True}
def obs(raw_slot='17:30',canonical_slot='17:30',raw_delay=10,canonical_delay=10,auth='user-refresh',status='OK',valid=True):
    return {'date':'2026-09-13','scheduledSlot':canonical_slot,'rawScheduledSlot':raw_slot,
            'rawDelaySeconds':raw_delay,'delaySeconds':canonical_delay,'authMode':auth,
            'status':status,'valid':valid,'categories':['Vlees','Bakkerij'],
            'stores':[store(1463),store(1348),store(1135)],'checkedAt':'2026-09-13T17:30:10+02:00'}

assert len(persist.RAW_SLOTS)==101 and persist.RAW_SLOTS[0]=='17:30' and persist.RAW_SLOTS[-1]=='22:30'
assert len(persist.SLOTS)==61 and persist.SLOTS[0]=='17:30' and persist.SLOTS[-1]=='22:30'
assert persist.valid_obs(obs())
assert not persist.valid_obs(obs(raw_delay=241))
assert not persist.valid_obs(obs(auth='anonymous'))
assert not persist.valid_obs(obs(status='INCOMPLETE'))
assert persist.exact_canonical_obs(obs())
assert not persist.exact_canonical_obs(obs(raw_slot='17:33',canonical_slot='17:30'))
assert not persist.exact_canonical_obs(obs(canonical_delay=241))

points=session.points_for(datetime(2026,9,13,12,0,tzinfo=ZoneInfo('Europe/Amsterdam')))
assert len(points)==141 and points[0].strftime('%H:%M')=='17:30' and points[-1].strftime('%H:%M')=='22:30'
assert sum(session.raw_due(p.hour*60+p.minute) for p in points)==101
assert sum(session.canonical_due(p.hour*60+p.minute) for p in points)==61

# Prove refresh-token rotation is sealed and reusable across a fresh session.
with tempfile.TemporaryDirectory() as td:
    old_state=os.environ.get('AH_TOKEN_STATE_FILE'); old_refresh=os.environ.get('AH_REFRESH_TOKEN')
    os.environ['AH_TOKEN_STATE_FILE']=str(Path(td)/'auth.json'); os.environ['AH_REFRESH_TOKEN']='unit-root-refresh'
    calls=[]; original_post=scanner.post
    def fake_post(path,body,token=None,attempts=2):
        calls.append((path,body.get('refreshToken')))
        return 200,{'access_token':'unit-access','expires_in':3600,'refresh_token':'unit-rotated-refresh'}
    scanner.post=fake_post
    try:
        a1,m1=scanner.token(); s1=scanner.LAST_AUTH_SOURCE
        a2,m2=scanner.token(); s2=scanner.LAST_AUTH_SOURCE
        assert (a1,a2,m1,m2,s1,s2)==('unit-access','unit-access','user-refresh','user-refresh','refresh','cache')
        assert calls==[('/mobile-auth/v1/auth/token/refresh','unit-root-refresh')]
        state=Path(os.environ['AH_TOKEN_STATE_FILE']); saved=json.loads(state.read_text())
        assert saved['refreshToken']=='unit-rotated-refresh' and (state.stat().st_mode & 0o777)==0o600
        sealed=Path(td)/'sealed.enc'; sealed.write_text(auth_state.seal_state_text('unit-root-refresh'))
        state.unlink(); assert auth_state.restore_state('unit-root-refresh',sealed)['refreshToken']=='unit-rotated-refresh'
    finally:
        scanner.post=original_post
        if old_state is None: os.environ.pop('AH_TOKEN_STATE_FILE',None)
        else: os.environ['AH_TOKEN_STATE_FILE']=old_state
        if old_refresh is None: os.environ.pop('AH_REFRESH_TOKEN',None)
        else: os.environ['AH_REFRESH_TOKEN']=old_refresh

# Independent scanner processes must reuse one valid cached access token.
with tempfile.TemporaryDirectory() as td:
    state=Path(td)/'auth.json'
    state.write_text(json.dumps({'accessToken':'cross-process-access','accessExpiresAt':int(time.time())+3600,'refreshToken':''}))
    os.chmod(state,0o600)
    env=dict(os.environ); env['AH_TOKEN_STATE_FILE']=str(state); env.pop('AH_REFRESH_TOKEN',None)
    code="import scanner; a,m=scanner.token(); assert a=='cross-process-access' and m=='user-refresh' and scanner.LAST_AUTH_SOURCE=='cache'"
    for _ in range(2): subprocess.run(['python','-c',code],cwd=ROOT,env=env,check=True)

print('scanner/session/persistence/token-rotation self-test: PASS')
