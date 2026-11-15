"""Opslag op de data-branch: één JSONL-bestand per dag, idempotent per scanmoment."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ah_scanner import slots
from ah_scanner.models import ScanResult

SCANS_DIR = "scans"


def day_file(root: Path, scheduled: datetime) -> Path:
    day = scheduled.astimezone(slots.TZ).date().isoformat()
    return root / SCANS_DIR / f"{day}.jsonl"


def read_day(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def append_scan(root: Path, scheduled: datetime, scan: ScanResult) -> bool:
    """Voeg een scan toe. Een scanmoment dat al bestaat wordt nooit overschreven (False)."""
    path = day_file(root, scheduled)
    if any(r["scheduled_at"] == scan.scheduled_at for r in read_day(path)):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(scan.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
    (root / "latest.json").write_text(
        json.dumps(scan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


def coverage(root: Path, day) -> tuple[int, int]:
    """(aantal geldige unieke scanmomenten, verwacht aantal) voor één dag."""
    expected = {s.isoformat() for s in slots.slots_for(day)}
    path = root / SCANS_DIR / f"{day.isoformat()}.jsonl"
    done = {r["scheduled_at"] for r in read_day(path) if r.get("valid")}
    return len(done & expected), len(expected)
