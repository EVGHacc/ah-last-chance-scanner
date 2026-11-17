"""Analyse-export: tabelbestanden (CSV) uit de v2-scans en de oude v1-data (legacy).

Twee nette tabellen per dag, in dezelfde kolomindeling voor v1 en v2:

- ``scans/<dag>.csv``: een rij per scan en winkel (gelukt, aantallen, status, vertraging).
- ``items/<dag>.csv``: een rij per scan, winkel en Vlees-aanbieding (alle percentages).

Let op: v1-scans liggen niet op een 5-minutenraster (1 tot 3 minuten uit elkaar) en de vroegste
v1-bestanden bevatten geen producten. ``canonical_5min`` markeert de scans op het 5-minutenraster
(17:30, 17:35, ...) zodat v1 en v2 vergelijkbaar zijn.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from ah_scanner.quality import assess

START_MIN, END_MIN, STEP_MIN = 17 * 60 + 30, 22 * 60 + 30, 5
LATE_AFTER_SECONDS = 240

SCAN_COLUMNS = [
    "source", "date", "scheduled_slot", "scheduled_at", "canonical_5min", "started_at",
    "completed_at", "delay_seconds", "late", "scan_status", "scan_valid", "store_id", "store",
    "fetched", "error", "total_items", "meat_items", "meat70_items",
]  # fmt: skip
ITEM_COLUMNS = [
    "source", "date", "scheduled_slot", "scheduled_at", "canonical_5min", "store_id", "store",
    "product_id", "title", "brand", "size", "category", "discount_pct", "stock", "price_was",
    "price_now", "expires", "is_70", "popular", "total_grams", "enough_for_four",
]  # fmt: skip

Row = dict[str, object]


def slot_of(scheduled_at: str) -> str:
    """HH:MM uit een ISO-tijdstempel (lokale tijd zoals opgeslagen)."""
    return scheduled_at[11:16] if len(scheduled_at) >= 16 else ""


def _quality_cells(title: object, size: object, stock: object) -> Row:
    q = assess(str(title or ""), str(size or ""), stock)
    return {
        "popular": q.popular,
        "total_grams": "" if q.total_grams is None else round(q.total_grams),
        "enough_for_four": "" if q.enough_for_four is None else q.enough_for_four,
    }


def canonical_5min(slot: str) -> bool:
    try:
        minutes = int(slot[:2]) * 60 + int(slot[3:5])
    except ValueError:
        return False
    return START_MIN <= minutes <= END_MIN and (minutes - START_MIN) % STEP_MIN == 0


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _rows_v2(record: dict) -> tuple[list[Row], list[Row]]:
    scheduled = str(record.get("scheduled_at") or "")
    slot = slot_of(scheduled)
    base = {
        "source": "v2", "date": scheduled[:10], "scheduled_slot": slot,
        "scheduled_at": scheduled, "canonical_5min": canonical_5min(slot),
    }  # fmt: skip
    scans, items = [], []
    for store in record.get("stores") or []:
        meat = store.get("meat_items") or []
        scans.append({
            **base, "started_at": record.get("started_at"),
            "completed_at": record.get("completed_at"),
            "delay_seconds": record.get("delay_seconds"), "late": record.get("late"),
            "scan_status": record.get("status"), "scan_valid": record.get("valid"),
            "store_id": store.get("store_id"), "store": store.get("store"),
            "fetched": store.get("fetched"), "error": store.get("error") or "",
            "total_items": store.get("total_items"), "meat_items": len(meat),
            "meat70_items": len(store.get("meat70") or []),
        })  # fmt: skip
        for item in meat:
            pct = _num(item.get("discount_pct"))
            items.append({
                **{k: base[k] for k in ITEM_COLUMNS if k in base},
                "store_id": store.get("store_id"), "store": store.get("store"),
                "product_id": item.get("product_id"), "title": item.get("title"),
                "brand": item.get("brand"), "size": item.get("size"),
                "category": item.get("category"), "discount_pct": pct,
                "stock": item.get("stock"), "price_was": item.get("price_was"),
                "price_now": item.get("price_now"), "expires": item.get("expires"),
                "is_70": pct is not None and pct >= 70,
                **_quality_cells(item.get("title"), item.get("size"), item.get("stock")),
            })  # fmt: skip
    return scans, items


def _rows_v1(record: dict) -> tuple[list[Row], list[Row]]:
    slot = str(record.get("scheduledSlot") or "")
    scheduled = str(record.get("scheduledAt") or "")
    delay = record.get("delaySeconds")
    base = {
        "source": "v1", "date": record.get("date") or scheduled[:10], "scheduled_slot": slot,
        "scheduled_at": scheduled, "canonical_5min": canonical_5min(slot),
    }  # fmt: skip
    scans, items = [], []
    for store in record.get("stores") or []:
        meat = store.get("items") or []
        scans.append({
            **base, "started_at": record.get("startedAt") or record.get("checkedAt"),
            "completed_at": record.get("completedAt"), "delay_seconds": delay,
            "late": (delay > LATE_AFTER_SECONDS) if isinstance(delay, int | float) else None,
            "scan_status": record.get("status"), "scan_valid": record.get("valid"),
            "store_id": store.get("storeId"), "store": store.get("store"),
            "fetched": store.get("fetched"), "error": store.get("error") or "",
            "total_items": store.get("totalBargainItems"),
            "meat_items": store.get("meatItems", len(meat)),
            "meat70_items": store.get("meat70Items"),
        })  # fmt: skip
        for item in meat:
            pct = _num(item.get("discountPct"))
            items.append({
                **{k: base[k] for k in ITEM_COLUMNS if k in base},
                "store_id": store.get("storeId"), "store": store.get("store"),
                "product_id": item.get("productId"), "title": item.get("title"),
                "brand": item.get("brand"), "size": item.get("size"),
                "category": item.get("category"), "discount_pct": pct,
                "stock": item.get("stock"), "price_was": item.get("priceWas"),
                "price_now": item.get("priceNow"), "expires": item.get("markdownExpirationDate"),
                "is_70": pct is not None and pct >= 70,
                **_quality_cells(item.get("title"), item.get("size"), item.get("stock")),
            })  # fmt: skip
    return scans, items


def rows_for(record: dict) -> tuple[list[Row], list[Row]] | None:
    """(scan-rijen, item-rijen), of None als het record geen bekend formaat heeft."""
    if "scheduled_at" in record and "stores" in record:
        return _rows_v2(record)
    if "scheduledSlot" in record and "stores" in record:
        return _rows_v1(record)
    return None


def _read_jsonl(path: Path) -> tuple[list[dict], int]:
    records, bad = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            bad += 1  # geldige JSON maar geen scan-object: tellen als overgeslagen
    return records, bad


def _write_csv(path: Path, columns: list[str], rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:  # BOM: opent goed in Excel
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_rows(data_root: Path) -> tuple[dict[str, list[Row]], dict[str, list[Row]], int]:
    """Lees v2 (``scans/*.jsonl``) en v1 (``legacy/????-??-??.jsonl``).

    Geeft (scanrijen per dag, itemrijen per dag, aantal overgeslagen regels); sleutel is YYYY-MM-DD.
    """
    files = sorted((data_root / "scans").glob("*.jsonl"))
    files += sorted((data_root / "legacy").glob("????-??-??.jsonl"))
    scans_by_day: dict[str, list[Row]] = defaultdict(list)
    items_by_day: dict[str, list[Row]] = defaultdict(list)
    skipped = 0
    for path in files:
        records, bad = _read_jsonl(path)
        skipped += bad
        for record in records:
            rows = rows_for(record)
            if rows is None:
                skipped += 1
                continue
            for row in rows[0]:
                scans_by_day[str(row["date"])].append(row)
            for row in rows[1]:
                items_by_day[str(row["date"])].append(row)
    return scans_by_day, items_by_day, skipped


def export_all(data_root: Path, out: Path, combined: bool = False) -> dict[str, int]:
    """Schrijf CSV per dag (scans en items) voor alle v1- en v2-data."""
    scans_by_day, items_by_day, skipped = load_rows(data_root)
    for day, rows in scans_by_day.items():
        _write_csv(out / "scans" / f"{day}.csv", SCAN_COLUMNS, rows)
        _write_csv(out / "items" / f"{day}.csv", ITEM_COLUMNS, items_by_day.get(day, []))
    if combined:
        all_scans = [r for d in sorted(scans_by_day) for r in scans_by_day[d]]
        all_items = [r for d in sorted(items_by_day) for r in items_by_day[d]]
        _write_csv(out / "scans_all.csv", SCAN_COLUMNS, all_scans)
        _write_csv(out / "items_all.csv", ITEM_COLUMNS, all_items)
    return {
        "days": len(scans_by_day),
        "scan_rows": sum(map(len, scans_by_day.values())),
        "item_rows": sum(map(len, items_by_day.values())),
        "skipped": skipped,
    }
