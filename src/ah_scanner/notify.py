"""Mail via Resend bij Vlees >= 70%, met deduplicatie per product/winkel/dag."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date
from pathlib import Path

from ah_scanner.models import Item, ScanResult

RESEND_URL = "https://api.resend.com/emails"
STATE_FILE = "notified.json"
KEEP_DAYS = 7

MailFn = Callable[[dict], bool]  # payload -> verzonden


def dedup_key(day: str, store_id: int, item: Item) -> str:
    return f"{day}|{store_id}|{item.product_id}|{item.expires}"


def load_state(root: Path) -> dict[str, list[str]]:
    try:
        return json.loads((root / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(root: Path, state: dict[str, list[str]], today: date) -> None:
    """Bewaar alleen de laatste KEEP_DAYS dagen."""
    keep = {d: k for d, k in state.items() if (today - date.fromisoformat(d)).days < KEEP_DAYS}
    (root / STATE_FILE).write_text(json.dumps(keep, sort_keys=True) + "\n", encoding="utf-8")


def new_items(scan: ScanResult, day: str, seen: set[str]) -> list[tuple[str, Item, str]]:
    """(winkel, item, sleutel) voor Vlees >= 70% dat nog niet gemeld is."""
    found = []
    for store in scan.stores:
        for item in store.meat70:
            key = dedup_key(day, store.store_id, item)
            if key not in seen:
                found.append((store.store, item, key))
    return found


def build_payload(
    found: list[tuple[str, Item, str]], scan: ScanResult, sender: str, to: str
) -> dict:
    lines = [
        f"- {store}: {i.title} ({i.size}) {i.discount_pct:.0f}% korting, "
        f"€{i.price_now} (was €{i.price_was}), voorraad {i.stock:g}"
        for store, i, _ in found
    ]
    note = (
        "" if scan.valid else f"\n\nLet op: scan-status {scan.status}; niet alle winkels gelezen."
    )
    if scan.late:
        note += f"\nLate scan: gepland {scan.scheduled_at}, gestart {scan.started_at}."
    return {
        "from": sender,
        "to": [to],
        "subject": f"AH Laatste Kans: {len(found)}x Vlees >= 70%",
        "text": "Nieuwe aanbiedingen:\n" + "\n".join(lines) + note,
    }


USER_AGENT = "ah-scanner/2.0 (+https://github.com/EVGHacc/ah-last-chance-scanner)"


def _error_name(exc: urllib.error.HTTPError) -> str:
    """Resend-foutnaam (bijv. 'validation_error'); nooit de body of adressen loggen."""
    try:
        name = json.loads(exc.read(2048)).get("name")
    except (ValueError, AttributeError, OSError):
        return "non_json"
    return name if isinstance(name, str) and name.isidentifier() else "unknown"


def resend_send(api_key: str) -> MailFn:
    def send(payload: dict) -> bool:
        req = urllib.request.Request(
            RESEND_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as exc:
            print(f"NOTIFY_ERROR http={exc.code} name={_error_name(exc)}")
            return False
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"NOTIFY_ERROR network={type(exc).__name__}")
            return False

    return send


def notify(scan: ScanResult, day: date, root: Path, send: MailFn, sender: str, to: str) -> str:
    """Geeft 'none', 'sent' of 'failed'. Sleutels worden pas na een geslaagde verzending bewaard."""
    state = load_state(root)
    seen = set(state.get(day.isoformat(), []))
    found = new_items(scan, day.isoformat(), seen)
    if not found:
        return "none"
    if not send(build_payload(found, scan, sender, to)):
        return "failed"
    state[day.isoformat()] = sorted(seen | {key for _, _, key in found})
    save_state(root, state, day)
    return "sent"
