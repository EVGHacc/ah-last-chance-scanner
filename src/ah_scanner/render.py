"""Opmaak van de mail: een kaart per product (HTML) met een tekstversie als terugval."""

from __future__ import annotations

from datetime import datetime
from html import escape

from ah_scanner.enrich import JA, NEE, Enrichment
from ah_scanner.models import Item, ScanResult
from ah_scanner.offers import Offer

FREEZE_LABEL = {JA: "Ja", NEE: "Nee"}
MAX_STORAGE_CHARS = 300


def eur(value: object) -> str:
    try:
        return f"€ {float(value):.2f}".replace(".", ",")  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value or "-")


def nl_date(value: str | None) -> str:
    parts = (value or "").split("-")
    return "-".join(reversed(parts)) if len(parts) == 3 else (value or "-")


def scan_day(scan: ScanResult) -> str | None:
    """Datum (YYYY-MM-DD, Amsterdam) van het scanmoment; None als die niet te lezen is."""
    try:
        return datetime.fromisoformat(scan.scheduled_at).date().isoformat()
    except ValueError:
        return None


def validity(item: Item, today: str | None) -> tuple[str, bool]:
    """(tekst, alleen_vandaag): 'Alleen vandaag' bij einddatum vandaag, anders 'Tot dd-mm-jjjj'."""
    if today and item.expires == today:
        return "Alleen vandaag", True
    return f"Tot {nl_date(item.expires)}", False


def freeze_label(info: Enrichment | None) -> str:
    return FREEZE_LABEL.get(info.freeze, "Onbekend") if info else "Onbekend"


def _storage(info: Enrichment | None) -> str:
    text = (info.storage if info else "")[:MAX_STORAGE_CHARS]
    return text


def _info(info: dict[int, Enrichment], item: Item) -> Enrichment | None:
    return info.get(item.product_id) if isinstance(item.product_id, int) else None


def summary_line(total: int, added: list[Offer], removed: list[Offer]) -> str:
    return f"Nu {total} aanbiedingen Vlees ≥ 70% · {len(added)} nieuw · {len(removed)} verdwenen"


def subject(total: int, added: list[Offer], removed: list[Offer]) -> str:
    return f"AH Laatste Kans: {total} aanbiedingen Vlees >= 70% (+{len(added)} / -{len(removed)})"


def _notes_text(scan: ScanResult, unread: list[str]) -> str:
    note = ""
    if unread:
        note += f"\n\nLet op: niet gelezen (laatst bekende stand getoond): {', '.join(unread)}."
    if scan.late:
        note += f"\nLate scan: gepland {scan.scheduled_at}, gestart {scan.started_at}."
    return note


def _offer_line(offer: Offer, info: dict[int, Enrichment], today: str | None) -> str:
    item, extra = offer.item, _info(info, offer.item)
    when = validity(item, today)[0].lower()
    line = (
        f"  {'[NIEUW] ' if offer.is_new else ''}{item.title} ({item.size}) "
        f"{item.discount_pct:.0f}% korting, {eur(item.price_now)} (was {eur(item.price_was)}), "
        f"voorraad {item.stock:g}, {when}, "
        f"invriesbaar: {freeze_label(extra)}"
    )
    if offer.stale:
        line += " (laatst bekend)"
    if _storage(extra):
        line += f"\n    Bewaren: {_storage(extra)}"
    return line


def render_text(
    offers: list[Offer],
    added: list[Offer],
    removed: list[Offer],
    unread: list[str],
    scan: ScanResult,
    info: dict[int, Enrichment],
) -> str:
    lines = [summary_line(len(offers), added, removed)]
    if removed:
        lines += ["", "Verdwenen sinds de vorige mail:"]
        lines += [f"  - {o.store}: {o.item.title} ({o.item.size})" for o in removed]
    for store in scan.stores:
        mine = [o for o in offers if o.store_id == store.store_id]
        lines += ["", f"{store.store} ({len(mine)})"]
        lines += [_offer_line(o, info, scan_day(scan)) for o in mine] or ["  Geen 70%-aanbiedingen"]
    return "\n".join(lines) + _notes_text(scan, unread)


def _card(offer: Offer, info: Enrichment | None, today: str | None) -> str:
    e, item = escape, offer.item
    image = (
        f'<img src="{e(info.image_url, quote=True)}" width="120" alt="{e(item.title)}" '
        'style="display:block;border-radius:8px;border:0">'
        if info and info.image_url
        else '<div style="width:120px;height:90px;background:#eee;border-radius:8px"></div>'
    )
    freeze = freeze_label(info)
    colour = {"Ja": "#1a7f37", "Nee": "#b42318"}.get(freeze, "#667085")
    storage = _storage(info)
    life = info.lifespan if info and info.lifespan else ""
    banner = (
        '<tr><td colspan="2" style="background:#1a7f37;color:#fff;font-weight:700;'
        'font-size:13px;letter-spacing:1px;padding:4px 10px;border-radius:8px">'
        "NIEUW</td></tr>"
        if offer.is_new
        else ""
    )
    stale = (
        '<div style="color:#b42318;font-size:12px">Laatst bekende stand (winkel niet gelezen)</div>'
        if offer.stale
        else ""
    )
    when, only_today = validity(item, today)
    when_html = (
        '<span style="background:#fef0c7;color:#b54708;border-radius:6px;padding:2px 8px;'
        f'font-size:12px;font-weight:700">{e(when.upper())}</span>'
        if only_today
        else f'<span style="font-size:13px">{e(when)}</span>'
    )
    rows = [
        f'<div style="font-weight:700;font-size:16px">{e(item.title)}</div>',
        f'<div style="color:#667085;font-size:13px">{e(item.brand)} · {e(item.size)}</div>',
        '<div style="margin:6px 0">'
        '<span style="background:#e6007e;color:#fff;border-radius:6px;padding:2px 8px;'
        f'font-weight:700">-{item.discount_pct:.0f}%</span> '
        f'<span style="font-size:18px;font-weight:700">{e(eur(item.price_now))}</span> '
        f'<span style="color:#667085;text-decoration:line-through">{e(eur(item.price_was))}</span>'
        "</div>",
        f'<div style="font-size:13px">voorraad {item.stock:g} · {when_html}</div>',
        '<div style="font-size:14px;margin-top:6px"><b>Invriesbaar:</b> '
        f'<span style="color:{colour};font-weight:700">{freeze}</span></div>',
        stale,
    ]
    if storage:
        rows.append(f'<div style="font-size:12px;color:#475467"><b>Bewaren:</b> {e(storage)}</div>')
    if life:
        rows.append(
            f'<div style="font-size:12px;color:#475467"><b>Houdbaarheid:</b> {e(life)}</div>'
        )
    return (
        '<table role="presentation" width="100%" style="border:1px solid #e4e7ec;'
        f'border-radius:12px;margin:0 0 12px;padding:10px">{banner}<tr>'
        f'<td width="130" valign="top">{image}</td>'
        f'<td valign="top">{"".join(rows)}</td></tr></table>'
    )


def render_html(
    offers: list[Offer],
    added: list[Offer],
    removed: list[Offer],
    unread: list[str],
    scan: ScanResult,
    info: dict[int, Enrichment],
) -> str:
    e = escape
    parts = [
        '<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:640px">',
        f'<h2 style="margin:0 0 8px">{e(summary_line(len(offers), added, removed))}</h2>',
    ]
    if removed:
        items = "".join(
            f"<li>{e(o.store)}: {e(o.item.title)} ({e(o.item.size)})</li>" for o in removed
        )
        parts.append(
            '<div style="background:#fef3f2;border-radius:8px;padding:8px 12px;margin:0 0 12px">'
            f'<b>Verdwenen sinds de vorige mail</b><ul style="margin:4px 0">{items}</ul></div>'
        )
    for store in scan.stores:
        mine = [o for o in offers if o.store_id == store.store_id]
        parts.append(f'<h3 style="margin:16px 0 8px">{e(store.store)} ({len(mine)})</h3>')
        parts += [_card(o, _info(info, o.item), scan_day(scan)) for o in mine] or [
            '<p style="color:#667085;margin:0 0 12px">Geen 70%-aanbiedingen</p>'
        ]
    notes = e(_notes_text(scan, unread).strip()).replace("\n", "<br>")
    if notes:
        parts.append(f'<p style="color:#b42318;font-size:13px">{notes}</p>')
    parts.append("</div>")
    return "".join(parts)
