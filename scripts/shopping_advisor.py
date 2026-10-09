#!/usr/bin/env python3
"""Read-only AH shopping advisor. Never alters scanner measurements."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

DATA = Path("data")
HISTORY = DATA / "central/derived/combined_70_lifetimes.json"
PRIORITY = ("kipfilet", "kipdij", "gehakt", "hamburger", "schnitzel", "worst", "kipborrel")
MIN_STOCK = 2

def priority(title):
    t = title.casefold()
    return next((len(PRIORITY) - i for i, word in enumerate(PRIORITY) if word in t), 0)

def eligible(item, day):
    try:
        return (item.get("category") == "Vlees"
                and float(item.get("stock") or 0) >= MIN_STOCK
                and float(item.get("discountPct") or 0) >= 25
                and item.get("markdownExpirationDate") in (day.isoformat(), (day + timedelta(days=1)).isoformat()))
    except (ValueError, TypeError):
        return False

def advise(observation, historical=None):
    if not (observation.get("valid") is True and observation.get("status") in ("OK", "OK_ZERO_ROWS")
            and observation.get("authMode") == "user-refresh"
            and "Vlees" in (observation.get("categories") or [])
            and 0 <= int(observation.get("rawDelaySeconds", observation.get("delaySeconds", 999))) <= 240):
        raise ValueError("No valid current observation; cannot give departure advice")
    day = date.fromisoformat(observation["date"])
    summary = (historical or {}).get("summary") or {}
    stores = []
    for store in observation.get("stores") or []:
        if store.get("fetched") is not True:
            continue
        items = [i for i in store.get("items") or [] if eligible(i, day)]
        items.sort(key=lambda i: (i["markdownExpirationDate"] == day.isoformat(),
                                  float(i.get("discountPct") or 0) >= 70,
                                  priority(i.get("title") or ""),
                                  float(i.get("stock") or 0)), reverse=True)
        now70 = [i for i in items if float(i.get("discountPct") or 0) >= 70 and i["markdownExpirationDate"] == day.isoformat()]
        pipeline = [i for i in items if 25 <= float(i.get("discountPct") or 0) < 70 and i["markdownExpirationDate"] == day.isoformat()]
        sid = str(store.get("storeId"))
        hist = summary.get(sid) or {}
        # Historical disappearance is a stock-availability proxy, NOT a 40->70 conversion probability.
        stores.append({"storeId": sid, "store": store.get("store"), "70_stock": sum(float(i["stock"]) for i in now70),
                       "pipeline_stock": sum(float(i["stock"]) for i in pipeline),
                       "multiple_pack_candidates": len(items),
                       "products": items[:8],
                       "historical_70_episodes": hist.get("episodes_70", 0),
                       "historical_disappearance_within_30m": hist.get("gone_within_30m"),
                       "score": round(sum(float(i["stock"]) * (2 if float(i.get("discountPct") or 0) >= 70 else .5)
                                          * (1 + .1 * priority(i.get("title") or "")) for i in items
                                          if i["markdownExpirationDate"] == day.isoformat()), 2)})
    stores.sort(key=lambda s: s["score"], reverse=True)
    return {"source": "current valid AH observation + labeled historical stock-lifetime data",
            "checkedAt": observation.get("checkedAt"), "date": observation["date"],
            "advice": "Check live stock before leaving; 19:00-19:30 is a provisional observation window, not a guaranteed optimum.",
            "stores": stores}

def self_test():
    obs = {"date":"2026-10-09","valid":True,"status":"OK","authMode":"user-refresh",
           "categories":["Vlees"],"delaySeconds":0,"stores":[{"storeId":1463,"store":"A","fetched":True,
           "items":[{"title":"kipdijfilet","category":"Vlees","stock":4,"discountPct":40,"markdownExpirationDate":"2026-10-09"},
                    {"title":"worst","category":"Vleeswaren","stock":10,"discountPct":70,"markdownExpirationDate":"2026-10-09"}]}]}
    result = advise(obs)
    assert result["stores"][0]["pipeline_stock"] == 4
    assert result["stores"][0]["70_stock"] == 0
    assert result["stores"][0]["multiple_pack_candidates"] == 1
    obs["valid"] = False
    try: advise(obs)
    except ValueError: pass
    else: raise AssertionError("Invalid scan accepted")
    print("shopping advisor tests PASS")

if __name__ == "__main__":
    if "--self-test" in sys.argv: self_test()
    else:
        obs = json.loads((DATA / "latest.json").read_text(encoding="utf-8"))
        hist = json.loads(HISTORY.read_text(encoding="utf-8")) if HISTORY.exists() else {}
        print(json.dumps(advise(obs, hist), ensure_ascii=False, indent=2))
