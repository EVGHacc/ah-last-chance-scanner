#!/usr/bin/env python3
"""Independent, read-only verification of published AH observations."""
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
START, END = 17 * 60 + 30, 22 * 60 + 30
STORE_IDS = {1463, 1348, 1135, 4046, 8728}


def slots(step):
    return [f"{m // 60:02d}:{m % 60:02d}" for m in range(START, END + 1, step)]


RAW, CANONICAL = slots(3), slots(5)


def verify(root=Path("data"), now=None, require_complete=False):
    now = now or datetime.now(TZ)
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    day = status.get("date")
    today = now.date().isoformat()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    if day != today and not (day == yesterday and now.hour == 0):
        raise AssertionError(f"STALE status date={day}; today={today}")
    if (status.get("authMode"), status.get("category"),
            status.get("rawExpected"), status.get("canonicalExpected")) != (
                "user-refresh", "Vlees", 101, 61):
        raise AssertionError("Incorrect status scope/auth/cadence")
    if set(status.get("stores") or []) != STORE_IDS:
        raise AssertionError("Incorrect store scope")

    seen_raw, seen_canonical = set(), set()
    bad = 0
    archive = root / f"{day}.jsonl"
    if not archive.is_file():
        raise AssertionError(f"Missing source archive {archive}")
    with archive.open(encoding="utf-8") as source:
        for line in source:
            try:
                item = json.loads(line)
                slot = item["rawScheduledSlot"]
                target = datetime.fromisoformat(item["rawScheduledAt"])
                start = datetime.fromisoformat(item["startedAt"])
                checked = datetime.fromisoformat(item["checkedAt"])
                delay = (start - target).total_seconds()
                stores = item.get("stores") or []
                fetched = {int(s["storeId"]) for s in stores if s.get("fetched") is True}
                valid = (
                    item.get("date") == day and slot in RAW + CANONICAL
                    and item.get("scheduledSlot") == slot
                    and item.get("scheduledAt") == item.get("rawScheduledAt")
                    and target.strftime("%Y-%m-%d %H:%M") == f"{day} {slot}"
                    and target.utcoffset() == target.astimezone(TZ).utcoffset()
                    and 0 <= delay <= 240
                    and abs(delay - int(item["rawDelaySeconds"])) <= 2
                    and abs(delay - int(item["delaySeconds"])) <= 2
                    and start <= checked and item.get("valid") is True
                    and item.get("status") in ("OK", "OK_ZERO_ROWS")
                    and item.get("authMode") == "user-refresh"
                    and "Vlees" in item.get("categories", [])
                    and fetched == STORE_IDS
                )
                if valid:
                    if slot in RAW:
                        seen_raw.add(slot)
                    if slot in CANONICAL:
                        seen_canonical.add(slot)
                else:
                    bad += 1
            except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError):
                bad += 1

    # Cross-check durable per-slot archive when present. It is intentionally
    # independent from the growing JSONL and makes future historical analysis
    # resilient to large-file/API retrieval limitations.
    slot_root = root / "raw" / day
    if slot_root.is_dir():
        durable_raw=set()
        for path in slot_root.glob("*.json"):
            try:
                item=json.loads(path.read_text(encoding="utf-8"))
                if item.get("date")==day and item.get("valid") is True and item.get("authMode")=="user-refresh":
                    slot=item.get("rawScheduledSlot")
                    if slot in RAW: durable_raw.add(slot)
            except (ValueError, TypeError, json.JSONDecodeError, OSError):
                bad += 1
        if durable_raw and not durable_raw.issubset(seen_raw):
            raise AssertionError("Durable per-slot archive disagrees with source JSONL")

    listed_raw = status.get("rawSeen") or []
    listed_can = status.get("canonicalSeen") or []
    inconsistencies = []
    if len(listed_raw) != len(set(listed_raw)) or set(listed_raw) != seen_raw:
        inconsistencies.append("raw status does not match independent source scan")
    if len(listed_can) != len(set(listed_can)) or set(listed_can) != seen_canonical:
        inconsistencies.append("canonical status does not match independent source scan")
    if set(status.get("rawMissing") or []) != set(RAW) - seen_raw:
        inconsistencies.append("rawMissing is inconsistent")
    if set(status.get("canonicalMissing") or []) != set(CANONICAL) - seen_canonical:
        inconsistencies.append("canonicalMissing is inconsistent")
    cutoff = END if (day != today or require_complete) else min(END, now.hour * 60 + now.minute - 4)
    overdue_raw = [s for s in RAW if 60 * int(s[:2]) + int(s[3:]) <= cutoff and s not in seen_raw]
    overdue_can = [s for s in CANONICAL if 60 * int(s[:2]) + int(s[3:]) <= cutoff and s not in seen_canonical]
    missing_raw = [s for s in RAW if s not in seen_raw]
    missing_can = [s for s in CANONICAL if s not in seen_canonical]
    complete = len(seen_raw) == 101 and len(seen_canonical) == 61
    usable = bool(seen_raw) and not inconsistencies
    report = {
        "date": day, "raw": len(seen_raw), "rawExpected": 101,
        "canonical": len(seen_canonical), "canonicalExpected": 61,
        "missingRaw": missing_raw, "missingCanonical": missing_can,
        "overdueRaw": overdue_raw, "overdueCanonical": overdue_can,
        "invalidRowsIgnored": bad, "inconsistencies": inconsistencies,
        "usable": usable,
        "quality": "complete" if complete else ("partial" if usable else "unusable"),
        "complete": complete,
    }
    print(json.dumps(report, ensure_ascii=False))
    if inconsistencies or not usable or (require_complete and not complete):
        raise AssertionError("Independent AH QA failed; see detailed report")
    return report


def self_test():
    day = "2026-09-13"
    expected = sorted(set(RAW + CANONICAL))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rows = []
        for slot in expected:
            at = datetime.fromisoformat(f"{day}T{slot}:00+02:00")
            rows.append(dict(
                date=day, rawScheduledSlot=slot, scheduledSlot=slot,
                rawScheduledAt=at.isoformat(), scheduledAt=at.isoformat(),
                startedAt=(at + timedelta(seconds=10)).isoformat(),
                checkedAt=(at + timedelta(seconds=15)).isoformat(),
                rawDelaySeconds=10, delaySeconds=10, valid=True, status="OK",
                authMode="user-refresh", categories=["Vlees", "Bakkerij"],
                stores=[dict(storeId=s, fetched=True) for s in STORE_IDS],
            ))
        def write(rows, raw, canonical, date=day):
            (root / f"{day}.jsonl").write_text(
                "".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
            (root / "status.json").write_text(json.dumps(dict(
                date=date, authMode="user-refresh", category="Vlees",
                rawExpected=101, canonicalExpected=61, stores=sorted(STORE_IDS),
                rawSeen=raw, canonicalSeen=canonical,
                rawMissing=[s for s in RAW if s not in raw],
                canonicalMissing=[s for s in CANONICAL if s not in canonical],
            )), encoding="utf-8")
        end = datetime.fromisoformat(day + "T22:35:00+02:00")
        write(rows, RAW, CANONICAL)
        assert verify(root, end, True)["complete"]
        write([x for x in rows if x["rawScheduledSlot"] != "19:25"],
              RAW, CANONICAL)
        try:
            verify(root, end, True)
            raise AssertionError("Forged status accepted")
        except AssertionError as exc:
            assert "QA failed" in str(exc)
        incomplete = [x for x in rows if x["rawScheduledSlot"] != "19:25"]
        write(incomplete, RAW, [s for s in CANONICAL if s != "19:25"])
        try:
            verify(root, end, True)
            raise AssertionError("Missing slot accepted")
        except AssertionError as exc:
            assert "QA failed" in str(exc)
        write(rows, RAW, CANONICAL, date="2026-09-12")
        try:
            verify(root, end, True)
            raise AssertionError("Stale date accepted")
        except AssertionError as exc:
            assert "STALE" in str(exc)
    print("Independent AH QA self-tests: PASS")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        verify(require_complete="--complete" in sys.argv)
