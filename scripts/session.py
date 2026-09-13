#!/usr/bin/env python3
import os
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
START=17*60+30
END=22*60+30
MAX_RECOVERY_AGE=240


def due(minute):
    return START<=minute<=END and ((minute-START)%3==0 or (minute-START)%5==0)


def points_for(date):
    out=[]
    for minute in range(START,END+1):
        if not due(minute): continue
        out.append(datetime(date.year,date.month,date.day,minute//60,minute%60,tzinfo=TZ))
    return out


def run_point(target):
    env=dict(os.environ)
    env['SCHEDULED_AT']=target.isoformat()
    scan=subprocess.run(['python','scanner.py'],env=env)
    if scan.returncode!=0:
        print(f'Scan failed for {target.isoformat()}; watchdog will retry while still honest',flush=True)
        return False
    publish=subprocess.run(['python','scripts/publish.py'])
    if publish.returncode!=0:
        print(f'Publish failed for {target.isoformat()}; next watchdog/session point can recover persistence',flush=True)
        return False
    return True


def main():
    today=datetime.now(TZ)
    points=points_for(today)
    print(f'Supervised AH session: {len(points)} intended union points, {START//60:02d}:{START%60:02d}-{END//60:02d}:{END%60:02d}',flush=True)
    for target in points:
        while True:
            now=datetime.now(TZ)
            delta=(target-now).total_seconds()
            if delta<=0: break
            time.sleep(min(delta,30))
        now=datetime.now(TZ)
        age=(now-target).total_seconds()
        if age>MAX_RECOVERY_AGE:
            print(f'Skipping irrecoverably late point {target.isoformat()} age={int(age)}s',flush=True)
            continue
        run_point(target)
    print('Supervised AH session finished',flush=True)


if __name__=='__main__': main()
