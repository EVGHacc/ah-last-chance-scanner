#!/usr/bin/env python3
"""Backfill durable AH raw slot history from immutable scan commits."""
import argparse, json, subprocess
from pathlib import Path

START=17*60+30; END=22*60+30
MISSING={"17:30","17:33","17:36"}
STORE_IDS={1463,1348,1135,4046,8728}

def expected_raw_slots():
    all_slots=[f"{m//60:02d}:{m%60:02d}" for m in range(START,END+1,3)]
    return [s for s in all_slots if s not in MISSING]

def git(*args):
    return subprocess.check_output(["git",*args],text=True).strip()

def validate_observation(o,date,slot):
    assert o.get("date")==date
    assert o.get("rawScheduledSlot")==slot
    assert o.get("scheduledSlot")==slot
    assert o.get("valid") is True
    assert o.get("status") in {"OK","OK_ZERO_ROWS"}
    assert o.get("authMode")=="user-refresh"
    assert "Vlees" in (o.get("categories") or [])
    assert int(o.get("rawDelaySeconds",o.get("delaySeconds",999999)))<=240
    fetched={int(s["storeId"]) for s in (o.get("stores") or []) if s.get("fetched") is True}
    assert STORE_IDS.issubset(fetched)

def find_commit(date,slot):
    subject=f"AH scan {date} {slot}"
    out=git("log","--all","--format=%H%x09%s","--fixed-strings","--grep",subject)
    matches=[line.split("\t",1)[0] for line in out.splitlines() if line.endswith("\t"+subject)]
    if len(matches)!=1:
        raise AssertionError(f"{slot}: expected exactly one immutable scan commit, got {len(matches)}")
    return matches[0]

def observation_from_commit(sha):
    return json.loads(git("show",f"{sha}:data/latest.json"))

def verify_backfill(root,date):
    expected={s.replace(":","")+".json" for s in expected_raw_slots()}
    actual={p.name for p in root.glob("*.json")}
    assert actual==expected, f"durable set mismatch missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
    for slot in expected_raw_slots():
        o=json.loads((root/f"{slot.replace(':','')}.json").read_text(encoding="utf-8"))
        validate_observation(o,date,slot)
    for forbidden in MISSING:
        assert not (root/f"{forbidden.replace(':','')}.json").exists()
    return {"date":date,"count":len(actual),"missingFabricated":False}

def cross_check_jsonl(date,root):
    archive=Path("data")/f"{date}.jsonl"
    rows={}
    for line in archive.read_text(encoding="utf-8").splitlines():
        try: o=json.loads(line)
        except json.JSONDecodeError: continue
        slot=o.get("rawScheduledSlot")
        if slot in expected_raw_slots() and o.get("valid") is True and o.get("authMode")=="user-refresh":
            rows.setdefault(slot,[]).append(o)
    assert set(rows)==set(expected_raw_slots()), f"JSONL raw slots disagree: {sorted(set(expected_raw_slots())-set(rows))}"
    for slot in expected_raw_slots():
        durable=json.loads((root/f"{slot.replace(':','')}.json").read_text(encoding="utf-8"))
        assert any(r.get("checkedAt")==durable.get("checkedAt") for r in rows[slot]), f"{slot}: durable observation not found in JSONL"

def cross_check_historical_views(date):
    final=find_commit(date,"22:30")
    status=json.loads(git("show",f"{final}:data/status.json"))
    today=json.loads(git("show",f"{final}:data/today.json"))
    assert status.get("rawSeen")==expected_raw_slots()
    assert status.get("rawMissing")==["17:30","17:33","17:36"]
    assert status.get("canonicalMissing")==["17:30","17:35"]
    assert today.get("presentSlots")==59
    assert today.get("missingSlots")==["17:30","17:35"]

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--date",default="2026-10-06"); ap.add_argument("--verify-only",action="store_true")
    a=ap.parse_args()
    if a.date!="2026-10-06": raise SystemExit("This repair is deliberately scoped to 2026-10-06")
    root=Path("data/raw")/a.date
    if not a.verify_only:
        root.mkdir(parents=True,exist_ok=True)
        for slot in expected_raw_slots():
            sha=find_commit(a.date,slot)
            obs=observation_from_commit(sha); validate_observation(obs,a.date,slot)
            path=root/f"{slot.replace(':','')}.json"
            payload=json.dumps(obs,ensure_ascii=False,separators=(",",":"))
            if path.exists():
                old=json.loads(path.read_text(encoding="utf-8"))
                assert old.get("checkedAt")==obs.get("checkedAt"), f"{slot}: refusing overwrite"
            else: path.write_text(payload,encoding="utf-8")
    report=verify_backfill(root,a.date)
    cross_check_jsonl(a.date,root)
    cross_check_historical_views(a.date)
    print(json.dumps({**report,"jsonl":True,"historicalStatusToday":True},ensure_ascii=False))

if __name__=="__main__": main()
