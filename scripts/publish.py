#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)


def main():
    latest_path=Path('data/latest.json')
    if not latest_path.exists(): raise SystemExit('data/latest.json ontbreekt')
    latest_text=latest_path.read_text(encoding='utf-8')
    obs=json.loads(latest_text)
    date=obs.get('date','unknown')
    slot=obs.get('rawScheduledSlot') or obs.get('scheduledSlot') or 'unknown'

    for attempt in range(1,4):
        run('git','fetch','origin','main')
        run('git','reset','--hard','origin/main')
        Path('data').mkdir(exist_ok=True)
        latest_path.write_text(latest_text,encoding='utf-8')
        run('python','scripts/persist.py')
        run('git','add','data/')
        if run('git','diff','--cached','--quiet',check=False).returncode==0:
            print('No data changes to publish')
            return
        run('git','commit','-m',f'AH scan {date} {slot}')
        pushed=run('git','push','origin','HEAD:main',check=False)
        if pushed.returncode==0:
            print(f'Published authenticated AH scan {date} {slot}')
            return
        print(f'Push race on attempt {attempt}; retrying from origin/main')

    raise SystemExit('Could not publish measurement after 3 attempts')


if __name__=='__main__': main()
