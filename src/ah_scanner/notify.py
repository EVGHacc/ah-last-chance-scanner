"""Mail via Resend bij Vlees >= 70%, met deduplicatie per product/winkel/dag."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date
from pathlib import Path

from ah_scanner import offers, render
from ah_scanner.enrich import Enrichment
from ah_scanner.models import Item, ScanResult

RESEND_URL = "https://api.resend.com/emails"
STATE_FILE = "mail_state.json"

MailFn = Callable[[dict], bool]  # payload -> verzonden


def load_state(root: Path) -> dict:
    """Laatst verstuurde stand: {"day": "YYYY-MM-DD", "items": {sleutel: entry}}."""
    try:
        data = json.loads((root / STATE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(root: Path, day: date, snapshot: offers.Snapshot) -> None:
    (root / STATE_FILE).write_text(
        json.dumps({"day": day.isoformat(), "items": snapshot}, ensure_ascii=False, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def build_payload(
    current: list[offers.Offer],
    added: list[offers.Offer],
    removed: list[offers.Offer],
    unread: list[str],
    scan: ScanResult,
    sender: str,
    to: str,
    info: dict[int, Enrichment] | None = None,
) -> dict:
    info = info or {}
    return {
        "from": sender,
        "to": [to],
        "subject": render.subject(len(current), added, removed),
        "text": render.render_text(current, added, removed, unread, scan, info),
        "html": render.render_html(current, added, removed, unread, scan, info),
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


EnrichFn = Callable[[list[Item]], dict[int, Enrichment]]


def notify(
    scan: ScanResult,
    day: date,
    root: Path,
    send: MailFn,
    sender: str,
    to: str,
    enrich: EnrichFn | None = None,
) -> str:
    """Geeft 'none', 'sent' of 'failed'.

    Een mail met alle geldende 70%-aanbiedingen per filiaal volgt zodra de stand verschilt van de
    vorige mail (aanbieding erbij of eraf). De nieuwe stand wordt pas bewaard na een geslaagde
    verzending. Verrijking (foto, bewaartekst) is best-effort en blokkeert de mail nooit.
    """
    if not any(store.fetched for store in scan.stores):
        return "none"  # niets gelezen: geen basis om te vergelijken
    state = load_state(root)
    previous = state.get("items", {}) if state.get("day") == day.isoformat() else {}
    current, unread = offers.build_current(scan, previous)
    added, removed = offers.diff(current, previous)
    if not added and not removed:
        return "none"
    current = offers.mark_new(current, added)
    info: dict[int, Enrichment] = {}
    if enrich is not None:
        try:
            info = enrich([o.item for o in current])
        except Exception as exc:  # noqa: BLE001 - verrijking mag de mail nooit blokkeren
            print(f"ENRICH_FAILED type={type(exc).__name__}")
    if not send(build_payload(current, added, removed, unread, scan, sender, to, info)):
        return "failed"
    save_state(root, day, offers.snapshot_of(current))
    return "sent"
