"""Opmaak van de mail: een kaart per product (HTML) met een tekstversie als terugval."""

from __future__ import annotations

from html import escape

from ah_scanner.enrich import JA, NEE, Enrichment
from ah_scanner.models import Item, ScanResult

Found = list[tuple[str, Item, str]]  # (winkel, item, dedup-sleutel)

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


def freeze_label(info: Enrichment | None) -> str:
    return FREEZE_LABEL.get(info.freeze, "Onbekend") if info else "Onbekend"


def _storage(info: Enrichment | None) -> str:
    text = (info.storage if info else "")[:MAX_STORAGE_CHARS]
    return text


def render_text(found: Found, scan: ScanResult, info: dict[int, Enrichment]) -> str:
    lines = []
    for store, item, _ in found:
        extra = info.get(item.product_id) if isinstance(item.product_id, int) else None
        line = (
            f"- {store}: {item.title} ({item.size}) {item.discount_pct:.0f}% korting, "
            f"{eur(item.price_now)} (was {eur(item.price_was)}), voorraad {item.stock:g}, "
            f"korting t/m {nl_date(item.expires)}, invriesbaar: {freeze_label(extra)}"
        )
        if _storage(extra):
            line += f"\n  Bewaren: {_storage(extra)}"
        lines.append(line)
    return "Nieuwe aanbiedingen:\n" + "\n".join(lines) + _notes_text(scan)


def _notes_text(scan: ScanResult) -> str:
    note = (
        "" if scan.valid else f"\n\nLet op: scan-status {scan.status}; niet alle winkels gelezen."
    )
    if scan.late:
        note += f"\nLate scan: gepland {scan.scheduled_at}, gestart {scan.started_at}."
    return note


def _card(store: str, item: Item, info: Enrichment | None) -> str:
    e = escape
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
    rows = [
        f'<div style="font-weight:700;font-size:16px">{e(item.title)}</div>',
        f'<div style="color:#667085;font-size:13px">{e(item.brand)} · {e(item.size)}</div>',
        '<div style="margin:6px 0">'
        f'<span style="background:#e6007e;color:#fff;border-radius:6px;padding:2px 8px;'
        f'font-weight:700">-{item.discount_pct:.0f}%</span> '
        f'<span style="font-size:18px;font-weight:700">{e(eur(item.price_now))}</span> '
        f'<span style="color:#667085;text-decoration:line-through">{e(eur(item.price_was))}</span>'
        "</div>",
        f'<div style="font-size:13px">{e(store)} · voorraad {item.stock:g} · '
        f"korting t/m {e(nl_date(item.expires))}</div>",
        f'<div style="font-size:14px;margin-top:6px"><b>Invriesbaar:</b> '
        f'<span style="color:{colour};font-weight:700">{freeze}</span></div>',
    ]
    if storage:
        rows.append(f'<div style="font-size:12px;color:#475467"><b>Bewaren:</b> {e(storage)}</div>')
    if life:
        rows.append(
            f'<div style="font-size:12px;color:#475467"><b>Houdbaarheid:</b> {e(life)}</div>'
        )
    return (
        '<table role="presentation" width="100%" style="border:1px solid #e4e7ec;'
        'border-radius:12px;margin:0 0 12px;padding:10px"><tr>'
        f'<td width="130" valign="top">{image}</td>'
        f'<td valign="top">{"".join(rows)}</td></tr></table>'
    )


def render_html(found: Found, scan: ScanResult, info: dict[int, Enrichment]) -> str:
    cards = "".join(
        _card(store, item, info.get(item.product_id) if isinstance(item.product_id, int) else None)
        for store, item, _ in found
    )
    notes = escape(_notes_text(scan).strip()).replace("\n", "<br>")
    note_html = f'<p style="color:#b42318;font-size:13px">{notes}</p>' if notes else ""
    return (
        '<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:640px">'
        f'<h2 style="margin:0 0 12px">AH Laatste Kans: {len(found)}x Vlees ≥ 70%</h2>'
        f"{cards}{note_html}</div>"
    )
