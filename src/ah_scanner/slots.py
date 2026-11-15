"""Scanmomenten: elke 5 minuten van 17:30 t/m 22:30 Europe/Amsterdam (61 per dag)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")
START_MIN = 17 * 60 + 30
END_MIN = 22 * 60 + 30
STEP_MIN = 5
LATE_AFTER_SECONDS = 240  # zelfde grens als de oude gate (delay <= 240 s)


def slots_for(day: date) -> list[datetime]:
    """Alle scanmomenten van één dag als tijdzone-bewuste datetimes (DST-correct)."""
    return [
        datetime(day.year, day.month, day.day, m // 60, m % 60, tzinfo=TZ)
        for m in range(START_MIN, END_MIN + 1, STEP_MIN)
    ]


def parse_scheduled_at(raw: str) -> datetime:
    """Parse een ISO-tijdstempel (ook met 'Z') naar Amsterdam-tijd; seconden worden genegeerd."""
    value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("scheduled_at mist tijdzone")
    return value.astimezone(TZ).replace(second=0, microsecond=0)


def validate_slot(scheduled: datetime) -> datetime:
    """Controleer dat het moment op het 5-minutenraster binnen het scanvenster ligt."""
    local = scheduled.astimezone(TZ)
    minutes = local.hour * 60 + local.minute
    if not (START_MIN <= minutes <= END_MIN) or (minutes - START_MIN) % STEP_MIN:
        raise ValueError(f"geen geldig scanmoment: {local.isoformat()}")
    return local


def delay_seconds(scheduled: datetime, started: datetime) -> int:
    return max(0, int((started - scheduled).total_seconds()))


def is_late(delay: int) -> bool:
    return delay > LATE_AFTER_SECONDS
