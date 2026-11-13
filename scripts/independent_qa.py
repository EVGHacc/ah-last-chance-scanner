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

    latest_path = root / "latest.json"
    if not latest_path.is_file():
        raise AssertionError(f"Missing latest observation {latest_path}")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest_slot = latest.get("rawScheduledSlot")
    if (latest.get("date") != day or latest_slot not in RAW + CANONICAL
            or latest.get("authMode") != "user-refresh"
            or latest.get("categories") != ["Vlees"]
            or latest.get("valid") is not True
            or latest.get("status") not in ("OK", "OK_ZERO_ROWS")):
        raise AssertionError("Latest observation is not a valid Vlees-only scan")
    if require_complete and latest_slot != "22:30":
        raise AssertionError("Complete publication does not contain the final 22:30 observation")
    try:
        latest_target = datetime.fromisoformat(latest["rawScheduledAt"])
        latest_started = datetime.fromisoformat(latest["startedAt"])
        latest_checked = datetime.fromisoformat(latest["checkedAt"])
        latest_delay = (latest_started - latest_target).total_seconds()
        latest_stores = latest.get("stores") or []
        latest_fetched = {
            int(store["storeId"]) for store in latest_stores
            if isinstance(store, dict) and store.get("fetched") is True
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AssertionError("Latest observation timing/store evidence is malformed")
    if (latest_target.tzinfo is None or latest_started.tzinfo is None or latest_checked.tzinfo is None
            or len(latest_stores) != len(STORE_IDS)
            or latest_target.strftime("%Y-%m-%d %H:%M") != f"{day} {latest_slot}"
            or latest_target.utcoffset() != latest_target.astimezone(TZ).utcoffset()
            or not 0 <= latest_delay <= 240
            or abs(latest_delay - int(latest.get("rawDelaySeconds", -999))) > 2
            or latest_started > latest_checked or latest_fetched != STORE_IDS):
        raise AssertionError("Latest observation timing or fetched-store evidence is invalid")
    status_latest = status.get("latestValid") or {}
    if (status_latest.get("checkedAt") != latest.get("checkedAt")
            or status_latest.get("rawScheduledSlot") != latest_slot):
        raise AssertionError("latest.json and status.json latestValid evidence disagree")

    seen_raw, seen_canonical = set(), set()
    seen_slots = set()
    archive_latest = None
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
                    and isinstance(item.get("categories"), list)
                    and len(item.get("categories")) == 1
                    and item.get("categories") == ["Vlees"]
                    and fetched == STORE_IDS
                )
                if valid:
                    if archive_latest is None or checked > archive_latest[0]:
                        archive_latest = (checked, item)
                    if slot in seen_slots:
                        bad += 1
                        continue
                    seen_slots.add(slot)
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

    if (archive_latest is None
            or archive_latest[1].get("checkedAt") != latest.get("checkedAt")
            or archive_latest[1].get("rawScheduledSlot") != latest_slot):
        raise AssertionError("latest.json does not match the newest valid JSONL observation")

    today_path = root / "today.json"
    if not today_path.is_file():
        raise AssertionError(f"Missing canonical publication {today_path}")
    today_view = json.loads(today_path.read_text(encoding="utf-8"))
    if (today_view.get("date") != day or today_view.get("expectedSlots") != 61
            or not isinstance(today_view.get("observations"), list)):
        raise AssertionError("Canonical publication date/schema is invalid")
    canonical_observations = today_view["observations"]
    canonical_slots = [item.get("scheduledSlot") for item in canonical_observations]
    if (today_view.get("presentSlots") != len(canonical_observations)
            or len(canonical_slots) != len(set(canonical_slots))
            or set(canonical_slots) != seen_canonical
            or set(today_view.get("missingSlots") or []) != set(CANONICAL) - seen_canonical):
        raise AssertionError("today.json does not match independently verified canonical slots")
    for item in canonical_observations:
        try:
            item_stores = {
                int(store["storeId"]) for store in (item.get("stores") or [])
                if isinstance(store, dict) and store.get("fetched") is True
            }
            item_delay = int(item.get("delaySeconds", 999999))
        except (TypeError, ValueError, KeyError):
            raise AssertionError("Canonical observation store/delay evidence is malformed")
        if (item.get("date") != day or item.get("rawScheduledSlot") != item.get("scheduledSlot")
                or item.get("scheduledSlot") not in CANONICAL
                or item.get("authMode") != "user-refresh"
                or item.get("categories") != ["Vlees"]
                or item.get("valid") is not True
                or not 0 <= item_delay <= 240
                or item_stores != STORE_IDS):
            raise AssertionError("Canonical observation violates Vlees/auth/store/slot contract")
    if require_complete and len(canonical_observations) != 61:
        raise AssertionError("Canonical publication is incomplete; expected 61/61")

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
    complete = len(seen_raw) == 101 and len(seen_canonical) == 61 and bad == 0
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
                authMode="user-refresh", categories=["Vlees"],
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
                latestValid=None if not rows else {
                    "checkedAt": rows[-1]["checkedAt"],
                    "rawScheduledSlot": rows[-1]["rawScheduledSlot"],
                },
            )), encoding="utf-8")
            if rows:
                (root / "latest.json").write_text(json.dumps(rows[-1]), encoding="utf-8")
            canonical_rows = [
                {
                    "date": row["date"], "scheduledSlot": row["scheduledSlot"],
                    "rawScheduledSlot": row["rawScheduledSlot"],
                    "authMode": row["authMode"], "categories": row["categories"],
                    "valid": row["valid"], "delaySeconds": row["delaySeconds"],
                    "stores": row["stores"],
                }
                for row in rows if row["scheduledSlot"] in CANONICAL
            ]
            canonical_present = {row["scheduledSlot"] for row in canonical_rows}
            (root / "today.json").write_text(json.dumps({
                "date": date, "expectedSlots": 61,
                "presentSlots": len(canonical_rows),
                "missingSlots": [slot for slot in CANONICAL if slot not in canonical_present],
                "observations": canonical_rows,
            }), encoding="utf-8")
        end = datetime.fromisoformat(day + "T22:35:00+02:00")
        write(rows, RAW, CANONICAL)
        assert verify(root, end, True)["complete"]
        mixed_category = [dict(item) for item in rows]
        mixed_category[-1]["categories"] = ["Vlees", "Bakkerij"]
        write(mixed_category, RAW, CANONICAL)
        try:
            verify(root, end, True)
            raise AssertionError("Mixed-category evidence accepted")
        except AssertionError as exc:
            if "Vlees-only" not in str(exc):
                raise
        else:
            raise AssertionError("Mixed-category latest observation accepted")
        write(rows, RAW, CANONICAL)
        today_payload = json.loads((root / "today.json").read_text(encoding="utf-8"))
        today_payload["presentSlots"] = 60
        (root / "today.json").write_text(json.dumps(today_payload), encoding="utf-8")
        try:
            verify(root, end, True)
            raise AssertionError("Mismatched canonical publication accepted")
        except AssertionError as exc:
            if "today.json" not in str(exc):
                raise
        write(rows, RAW, CANONICAL)
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
