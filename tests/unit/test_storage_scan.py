import json
from datetime import date, datetime, timedelta

import pytest

from ah_scanner import auth, cli, slots, storage
from ah_scanner.models import OK, ScanResult

from .test_client import ok_payload
from .test_filters_slots import row

SCHED = datetime(2026, 11, 15, 17, 30, tzinfo=slots.TZ)


def scan_result(sched=SCHED, status=OK):
    return ScanResult(sched.isoformat(), sched.isoformat(), sched.isoformat(), 0, False, status)


def test_append_is_idempotent_per_slot(tmp_path):
    assert storage.append_scan(tmp_path, SCHED, scan_result())
    assert not storage.append_scan(tmp_path, SCHED, scan_result())
    assert len(storage.read_day(storage.day_file(tmp_path, SCHED))) == 1
    assert json.loads((tmp_path / "latest.json").read_text())["status"] == OK


def test_coverage_telt_alleen_geldige_unieke_slots(tmp_path):
    for i, s in enumerate(slots.slots_for(date(2026, 11, 15))[:3]):
        storage.append_scan(tmp_path, s, scan_result(s, OK if i < 2 else "INCOMPLETE"))
    assert storage.coverage(tmp_path, date(2026, 11, 15)) == (2, 61)


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_REFRESH_TOKEN", "secret")
    return tmp_path


def good_post(path, body):
    return 200, {"access_token": "acc", "refresh_token": "rot"}


def test_scan_ok_slaat_late_scan_op_met_echte_tijd(env):
    started = SCHED + timedelta(hours=3)
    code = cli.scan(
        SCHED.isoformat(),
        env / "s.enc",
        env / "d",
        good_post,
        lambda s, a: ok_payload(row(pct=90)),
        lambda: started,
    )
    assert code == 0
    saved = storage.read_day(storage.day_file(env / "d", SCHED))[0]
    assert saved["late"] is True and saved["started_at"] == started.isoformat()
    assert saved["scheduled_at"] == SCHED.isoformat()
    assert auth.unseal(env / "s.enc", "secret") == "rot"  # rotatie bewaard


def test_scan_ongeldig_slot_wordt_geweigerd(env):
    code = cli.scan("2026-11-15T17:33:00+01:00", env / "s.enc", env / "d", good_post)
    assert code == cli.EXIT_SCAN_INVALID and not (env / "d").exists()


def test_scan_incomplete_is_nooit_groen(env):
    def gql(store, access):
        return (500, {}) if store == "8728" else ok_payload(row())

    code = cli.scan(SCHED.isoformat(), env / "s.enc", env / "d", good_post, gql, lambda: SCHED)
    assert code == cli.EXIT_SCAN_INVALID
    assert storage.read_day(storage.day_file(env / "d", SCHED))[0]["status"] == "INCOMPLETE"


def test_scan_zonder_geldige_auth_is_failed_en_opgeslagen(env):
    code = cli.scan(
        SCHED.isoformat(),
        env / "s.enc",
        env / "d",
        lambda p, b: (401, {}),
        lambda s, a: ok_payload(),
        lambda: SCHED,
    )
    assert code == cli.EXIT_SCAN_INVALID
    saved = storage.read_day(storage.day_file(env / "d", SCHED))[0]
    assert saved["status"] == "FAILED"
