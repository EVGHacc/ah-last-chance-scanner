from datetime import date, datetime, timedelta

import pytest

from ah_scanner import filters, slots


def row(cat="Vlees", pct=70, stock=1):
    return {
        "product": {"id": 1, "title": "x", "brand": "AH", "salesUnitSize": "1 kg"},
        "categoryTitle": cat,
        "markdown": {"markdownPercentage": pct, "markdownExpirationDate": "2026-11-15"},
        "stock": stock,
        "bargainPrice": {"priceWas": "5.00", "priceNow": "1.50"},
    }


def test_69_nee_70_ja():
    items = filters.meat_items([row(pct=69), row(pct=70), row(pct=85)])
    assert [i.discount_pct for i in filters.meat70(items)] == [70.0, 85.0]


def test_vlees_exact_niet_vleeswaren():
    rows = [row("Vlees"), row("Vleeswaren"), row("Bakkerij"), row(" vlees ")]
    assert len(filters.meat_items(rows)) == 2


def test_onleesbare_korting_telt_als_nul():
    items = filters.meat_items([row(pct="n.v.t."), row(pct=None)])
    assert filters.meat70(items) == []


@pytest.mark.parametrize("day", [date(2026, 11, 15), date(2026, 10, 25), date(2027, 3, 28)])
def test_61_slots_per_dag_ook_rond_dst(day):
    result = slots.slots_for(day)
    assert len(result) == 61
    assert (result[0].hour, result[0].minute) == (17, 30)
    assert (result[-1].hour, result[-1].minute) == (22, 30)


def test_dst_utc_offset_wisselt():
    winter = slots.slots_for(date(2026, 11, 15))[0]
    summer = slots.slots_for(date(2026, 7, 15))[0]
    assert winter.utcoffset() == timedelta(hours=1)
    assert summer.utcoffset() == timedelta(hours=2)


def test_parse_utc_naar_amsterdam():
    parsed = slots.parse_scheduled_at("2026-07-15T15:30:42Z")
    assert (parsed.hour, parsed.minute, parsed.second) == (17, 30, 0)


def test_naive_tijd_geweigerd():
    with pytest.raises(ValueError):
        slots.parse_scheduled_at("2026-11-15T17:30:00")


@pytest.mark.parametrize("hhmm", [(17, 25), (22, 35), (17, 33), (3, 0)])
def test_ongeldig_slot(hhmm):
    with pytest.raises(ValueError):
        slots.validate_slot(datetime(2026, 11, 15, *hhmm, tzinfo=slots.TZ))


def test_late_grens():
    assert not slots.is_late(240)
    assert slots.is_late(241)
    start = datetime(2026, 11, 15, 17, 30, tzinfo=slots.TZ)
    assert slots.delay_seconds(start, start + timedelta(hours=3)) == 10800
    assert slots.delay_seconds(start, start - timedelta(seconds=5)) == 0
