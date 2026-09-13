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
RETRY_DELAYS=(0,8,20)


def due(minute):
    return START<=minute<=END and ((minute-START)%3==0 or (minute-START)%5==0)


def points_for(date):
    return [datetime(date.year,date.month,date.day,m//60,m%60,tzinfo=TZ)
            for m in range(START,END+1) if due(m)]


def run_point(target):
    env=dict(os.environ)
    env['SCHEDULED_AT']=target.isoformat()
    for attempt,delay in enumerate(RETRY_DELAYS,1):
        if delay:
            time.sleep(delay)
        age=(datetime.now(TZ)-target).total_seconds()
        if age>MAX_RECOVERY_AGE:
            print(f'Point {target.isoformat()} no longer honestly recoverable after attempt {attempt-1}',flush=True)
            return False
        scan=subprocess.run(['python','scanner.py'],env=env)
        if scan.returncode!=0:
            print(f'Scan attempt {attempt} failed for {target.isoformat()}',flush=True)
            continue
        publish=subprocess.run(['python','scripts/publish.py'])
        if publish.returncode==0:
            return True
        print(f'Publish attempt {attempt} failed for {target.isoformat()}',flush=True)
    print(f'Point {target.isoformat()} left to independent watchdog',flush=True)
    return False


def main():
    today=datetime.now(TZ)
    points=points_for(today)
    print(f'Supervised AH session: {len(points)} intended union points, 17:30-22:30 Europe/Amsterdam',flush=True)
    for target in points:
        while True:
            delta=(target-datetime.now(TZ)).total_seconds()
            if delta<=0:
                break
            time.sleep(min(delta,30))
        age=(datetime.now(TZ)-target).total_seconds()
        if age>MAX_RECOVERY_AGE:
            print(f'Skipping irrecoverably late point {target.isoformat()} age={int(age)}s',flush=True)
            continue
        run_point(target)
    print('Supervised AH session finished',flush=True)


if __name__=='__main__': main()
