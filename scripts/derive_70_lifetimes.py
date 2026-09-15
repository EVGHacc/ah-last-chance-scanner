#!/usr/bin/env python3
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

STORE_IDS = {"1463", "1348", "1135"}
VALID_STATUS = {"OK", "OK_ZERO_ROWS"}
DATA = Path("data")
CENTRAL = DATA / "central" / "derived"
HISTORICAL = CENTRAL / "historical_70_lifetimes.json"
CURRENT_OUT = CENTRAL / "current_70_lifetimes.json"
COMBINED_OUT = CENTRAL / "combined_70_lifetimes.json"


def parse_dt(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def percentile(values, p):
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return round(xs[0], 1)
    pos = (len(xs) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return round(xs[lo] * (1 - frac) + xs[hi] * frac, 1)


def valid_obs(o):
    if not isinstance(o, dict):
        return False
    if o.get("authMode") != "user-refresh":
        return False
    if o.get("status") not in VALID_STATUS or o.get("valid") is not True:
        return False
    try:
        delay = int(o.get("rawDelaySeconds", o.get("delaySeconds", 999999)))
    except Exception:
        return False
    if delay > 240:
        return False
    if "Vlees" not in (o.get("categories") or []):
        return False
    stores = o.get("stores") or []
    fetched = {
        str(s.get("storeId"))
        for s in stores
        if s.get("fetched") is True and s.get("storeId") is not None
    }
    return fetched == STORE_IDS


def obs_rank(o):
    """Prefer the least-delayed observation for one intended raw timestamp; break ties by earliest completion."""
    try:
        delay = int(o.get("rawDelaySeconds", o.get("delaySeconds", 999999)))
    except Exception:
        delay = 999999
    return delay, str(o.get("checkedAt") or "")


def horizon_rate(rows, horizon):
    eligible = [
        r for r in rows
        if (r.get("event") and r.get("minutes") is not None and r["minutes"] <= horizon)
        or (r.get("followup_minutes") or 0) >= horizon
    ]
    if not eligible:
        return {"eligible": 0, "gone": 0, "pct": None}
    gone = sum(
        1 for r in eligible
        if r.get("event") and r.get("minutes") is not None and r["minutes"] <= horizon
    )
    return {"eligible": len(eligible), "gone": gone, "pct": round(100 * gone / len(eligible), 1)}


def make_summary(rows):
    events = [r for r in rows if r.get("event") and r.get("minutes") is not None]
    vals = [float(r["minutes"]) for r in events]
    return {
        "episodes_70": len(rows),
        "confirmed_persistent_disappearances": len(events),
        "right_censored": len(rows) - len(events),
        "event_rate_pct": round(100 * len(events) / len(rows), 1) if rows else None,
        "mean_minutes_events_only": round(sum(vals) / len(vals), 1) if vals else None,
        "median_minutes_events_only": percentile(vals, 0.5),
        "p25_minutes_events_only": percentile(vals, 0.25),
        "p75_minutes_events_only": percentile(vals, 0.75),
        "gone_within_15m": horizon_rate(rows, 15),
        "gone_within_30m": horizon_rate(rows, 30),
        "gone_within_60m": horizon_rate(rows, 60),
        "gone_within_90m": horizon_rate(rows, 90),
    }


def summarize(episodes):
    out = {
        store: make_summary([r for r in episodes if str(r.get("store_id")) == store])
        for store in sorted(STORE_IDS)
    }
    out["all"] = make_summary(episodes)
    return out


def current_episodes():
    # First select exactly one best valid observation for each intended raw timestamp.
    selected = {}
    current_files = sorted(DATA.glob("2026-*.jsonl"))
    for path in current_files:
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if not valid_obs(o):
                    continue
                date = str(o.get("date") or "")
                scheduled = o.get("rawScheduledAt") or o.get("scheduledAt") or o.get("checkedAt")
                if not date or not scheduled:
                    continue
                try:
                    ts = parse_dt(scheduled)
                except Exception:
                    continue
                key = (date, ts)
                previous = selected.get(key)
                if previous is None or obs_rank(o) < obs_rank(previous):
                    selected[key] = o

    presence = defaultdict(set)
    scan_times = defaultdict(set)
    product_names = {}
    stock_at = {}
    discount_at = {}
    coverage = defaultdict(lambda: {store: 0 for store in sorted(STORE_IDS)})

    for (date, ts), o in sorted(selected.items()):
        for s in o.get("stores") or []:
            store = str(s.get("storeId") or "")
            if store not in STORE_IDS or s.get("fetched") is not True:
                continue
            scan_times[(date, store)].add(ts)
            coverage[date][store] += 1
            key_scan = (date, store, ts)
            for item in s.get("items") or []:
                if str(item.get("category") or "").strip() != "Vlees":
                    continue
                product = str(item.get("productId") or "")
                if not product:
                    continue
                presence[key_scan].add(product)
                product_names[(date, store, product)] = item.get("title") or ""
                key = (date, store, product, ts)
                try:
                    stock_at[key] = float(item.get("stock")) if item.get("stock") is not None else None
                except Exception:
                    stock_at[key] = None
                try:
                    discount_at[key] = float(item.get("discountPct") or 0)
                except Exception:
                    discount_at[key] = 0.0

    episodes = []
    keys = set((d, s, p) for (d, s, p, _t) in discount_at)
    for date, store, product in sorted(keys):
        times = sorted(scan_times[(date, store)])
        obs70 = sorted(
            t for (d, s, p, t), disc in discount_at.items()
            if d == date and s == store and p == product and disc >= 69.5
        )
        if not obs70:
            continue
        t0 = obs70[0]
        later = [t for t in times if t > t0]
        base = {
            "date": date,
            "store_id": store,
            "product_id": product,
            "product": product_names.get((date, store, product), ""),
            "source": "current-scanner-v5",
            "first70": t0.isoformat(),
            "stock_at_70": stock_at.get((date, store, product, t0)),
        }
        if not later:
            episodes.append({
                **base, "event": False, "minutes": None,
                "last_followup": t0.isoformat(), "followup_minutes": 0.0,
                "reason": "no_later_valid_scan"
            })
            continue

        disappeared = None
        for i, t in enumerate(later):
            if product in presence[(date, store, t)]:
                continue
            if all(product not in presence[(date, store, u)] for u in later[i:]):
                disappeared = t
                break

        last = later[-1]
        if disappeared is not None:
            episodes.append({
                **base,
                "event": True,
                "first_persistent_absence": disappeared.isoformat(),
                "minutes": round((disappeared - t0).total_seconds() / 60, 2),
                "last_followup": last.isoformat(),
                "followup_minutes": round((last - t0).total_seconds() / 60, 2),
                "reason": "persistent_absence_proxy_not_proof_of_sale",
            })
        else:
            episodes.append({
                **base,
                "event": False,
                "minutes": None,
                "last_followup": last.isoformat(),
                "followup_minutes": round((last - t0).total_seconds() / 60, 2),
                "reason": "still_present_at_last_valid_scan",
            })

    coverage_out = {
        date: {"valid_scans_by_store": dict(stores)}
        for date, stores in sorted(coverage.items())
    }
    return episodes, coverage_out, [p.name for p in current_files], len(selected)


def main():
    CENTRAL.mkdir(parents=True, exist_ok=True)
    current, current_coverage, files, selected_count = current_episodes()
    current_payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "method": {
            "scope": "valid scanner-v5 raw observations",
            "event": "first later valid store scan where a >=70% product is absent and never reappears that day",
            "interpretation": "persistent disappearance is a depletion proxy; it may be sale, staff removal or an inventory/API effect and is not proof of sale",
            "censoring": "products still present at the last valid scan are right-censored",
            "validity": "user-refresh, valid=true, status OK/OK_ZERO_ROWS, delay<=240s, all three stores fetched, category exact Vlees",
            "deduplication": "one best observation per intended raw timestamp; lowest delay then earliest checkedAt",
        },
        "coverage": current_coverage,
        "source_files": files,
        "selected_raw_observations": selected_count,
        "summary": summarize(current),
        "episodes": current,
    }
    CURRENT_OUT.write_text(json.dumps(current_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    historical = []
    historical_meta = None
    if HISTORICAL.exists():
        hist_payload = json.loads(HISTORICAL.read_text(encoding="utf-8"))
        historical = list(hist_payload.get("episodes") or [])
        historical_meta = {
            "generated_at": hist_payload.get("generated_at"),
            "provenance": hist_payload.get("provenance"),
            "method": hist_payload.get("method"),
        }

    dedup = {}
    for row in historical + current:
        key = (
            str(row.get("date")), str(row.get("store_id")), str(row.get("product_id")),
            str(row.get("first70")), str(row.get("source")),
        )
        dedup[key] = row
    combined = sorted(
        dedup.values(),
        key=lambda r: (str(r.get("date")), str(r.get("store_id")), str(r.get("first70")), str(r.get("product_id")))
    )

    combined_payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "method": {
            "event": "persistent disappearance proxy after first >=70% observation",
            "interpretation": "not proof of sale; possible sale, staff removal or inventory/API effect",
            "censoring": "right-censored episodes are retained and excluded from event-only mean/median",
            "historical_scope": "product-level observer scans only; counts-only official backfills excluded",
            "current_scope": "valid scanner-v5 raw observations, deduplicated per intended timestamp",
        },
        "historical_loaded": HISTORICAL.exists(),
        "historical_meta": historical_meta,
        "summary": summarize(combined),
        "episodes": combined,
    }
    COMBINED_OUT.write_text(json.dumps(combined_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "historical_loaded": HISTORICAL.exists(),
        "historical_episodes": len(historical),
        "current_episodes": len(current),
        "selected_raw_observations": selected_count,
        "combined_episodes": len(combined),
        "summary": combined_payload["summary"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
