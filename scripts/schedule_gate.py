#!/usr/bin/env python3
"""Amsterdam/DST-safe gate for redundant GitHub AH evening starters."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
SLOTS=((16,'47,53,59'),(17,'7,13,19'),(18,'11,17,23'))


def allowed(event, schedule, now):
    minute=now.hour*60+now.minute
    if not (16*60+40<=minute<=22*60+20):
        return False
    if event!='schedule':
        return event in ('push','workflow_dispatch')
    offset=int(now.utcoffset().total_seconds()//3600)
    expected={f'{minutes} {hour-offset} * * *' for hour,minutes in SLOTS}
    return schedule in expected


def self_test():
    summer=datetime(2026,7,10,20,56,tzinfo=TZ)
    winter=datetime(2027,1,10,20,56,tzinfo=TZ)
    for now in (summer,winter):
        offset=int(now.utcoffset().total_seconds()//3600)
        for hour,mins in SLOTS:
            assert allowed('schedule',f'{mins} {hour-offset} * * *',now)
        assert not allowed('schedule','0 3 * * *',now)
        assert allowed('workflow_dispatch','',now)
        assert not allowed('schedule',f'47,53,59 {14 if offset==1 else 15} * * *',now)
    assert not allowed('push','',datetime(2026,7,10,16,39,tzinfo=TZ))
    assert not allowed('schedule','47,53,59 14 * * *',datetime(2026,7,10,22,21,tzinfo=TZ))
    print('AH scheduler DST and delayed-start tests: PASS')


if __name__=='__main__':
    if '--self-test' in sys.argv:
        self_test()
    else:
        now=datetime.now(TZ)
        event=os.getenv('EVENT_NAME','')
        schedule=os.getenv('EVENT_SCHEDULE','')
        run=allowed(event,schedule,now)
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:
            f.write(f'run={str(run).lower()}\n')
        print('Amsterdam=',now.isoformat(),'event=',event,'schedule=',schedule,'run=',run)
