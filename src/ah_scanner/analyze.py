"""Wekelijkse trendanalyse op alle opgeslagen scans (v1 en v2).

Een *aanbieding* is een combinatie van dag, winkel, product en einddatum van de korting
("aanbieding-dag"). Alle cijfers komen uit de opgeslagen scans; er wordt niets geschat.

Maatstaven:

- alleen *volledige dagen* (eerste scan uiterlijk 17:45 en laatste scan vanaf 22:15) tellen mee
  voor tijdstippen en gemiddelden per dag; onvolledige dagen vertekenen die cijfers;
- eerste moment op >= 70% (wat bij de eerste scan al op 70% stond is niet te dateren);
- aantal aanbiedingen, aantal stuks (hoogste voorraad op 70%) en aanbiedingen die geschikt zijn
  voor vier personen: gewicht per pak maal voorraad >= ``FOUR_PERSON_GRAMS`` (500 g, 125 g p.p.).
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from html import escape
from pathlib import Path

from ah_scanner import export
from ah_scanner.quality import FOUR_PERSON_GRAMS, grams_of, popular_kind

COMPLETE_START_BY = "17:45"  # eerste scan van de dag uiterlijk hier, anders onvolledige start
COMPLETE_END_FROM = "22:15"  # laatste scan van de dag minimaal hier, anders onvolledig einde
MIN_DAYS_RELIABLE = 4  # minder dagen per groep: expliciet als weinig data markeren
BIN_MINUTES = 30
WEEKDAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


def _minutes(slot: str) -> int:
    return int(slot[:2]) * 60 + int(slot[3:5])


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass
class Offer:
    day: str
    store_id: str
    store: str
    product_id: str
    title: str
    size: str
    expires: str
    first70: str
    stock: float
    grams_pack: float | None
    at_day_start: bool  # al op 70% bij de eerste scan van de dag

    @property
    def total_grams(self) -> float | None:
        return None if self.grams_pack is None else self.grams_pack * self.stock

    @property
    def suitable4(self) -> bool | None:
        total = self.total_grams
        return None if total is None else total >= FOUR_PERSON_GRAMS

    @property
    def popular(self) -> bool:
        return bool(popular_kind(self.title))

    @property
    def top(self) -> bool:
        return self.popular and self.suitable4 is True


@dataclass
class Analysis:
    days: dict[str, dict] = field(default_factory=dict)  # dag -> {start, scans, complete_start}
    offers: list[Offer] = field(default_factory=list)
    skipped: int = 0
    sources: dict[str, int] = field(default_factory=dict)  # bron -> aantal scanrijen


def build(data_root: Path) -> Analysis:
    scans_by_day, items_by_day, skipped = export.load_rows(data_root)
    result = Analysis(skipped=skipped)
    for day, rows in scans_by_day.items():
        slots = sorted({str(r["scheduled_slot"]) for r in rows if r["scheduled_slot"]})
        start, end = (slots[0], slots[-1]) if slots else ("", "")
        result.days[day] = {
            "start": start,
            "end": end,
            "scans": len(slots),
            "complete": bool(slots) and start <= COMPLETE_START_BY and end >= COMPLETE_END_FROM,
        }
        for row in rows:
            result.sources[str(row["source"])] = result.sources.get(str(row["source"]), 0) + 1
    for day, rows in items_by_day.items():
        start = result.days.get(day, {}).get("start", "")
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for row in rows:
            if row["is_70"] and row["scheduled_slot"]:
                key = (row["store_id"], row["product_id"], row["expires"])
                groups[key].append(row)
        for (store_id, product_id, expires), hits in groups.items():
            first = min(hits, key=lambda r: str(r["scheduled_slot"]))
            stock = max((_num(r["stock"]) or 0.0) for r in hits)
            result.offers.append(
                Offer(
                    day, str(store_id), str(first["store"]), str(product_id), str(first["title"]),
                    str(first["size"] or ""), str(expires or ""), str(first["scheduled_slot"]),
                    stock, grams_of(first["size"]), str(first["scheduled_slot"]) == start,
                )
            )  # fmt: skip
    return result


def complete_days(analysis: Analysis) -> list[str]:
    return sorted(d for d, info in analysis.days.items() if info["complete"])


def _weekday(day: str) -> str:
    return WEEKDAYS[date.fromisoformat(day).weekday()]


def _per_day(offers: list[Offer], days: list[str]) -> dict:
    """Totalen en gemiddelden per dag voor een groep aanbiedingen over ``days``."""
    n = len(days)
    suit = [o for o in offers if o.suitable4]
    popular = [o for o in offers if o.popular]
    top = [o for o in offers if o.top]
    return {
        "days": n,
        "offers": len(offers),
        "offers_per_day": len(offers) / n if n else 0.0,
        "stock": sum(o.stock for o in offers),
        "stock_per_day": sum(o.stock for o in offers) / n if n else 0.0,
        "suitable4": len(suit),
        "suitable4_per_day": len(suit) / n if n else 0.0,
        "popular": len(popular),
        "popular_per_day": len(popular) / n if n else 0.0,
        "top": len(top),
        "top_per_day": len(top) / n if n else 0.0,
        "reliable": n >= MIN_DAYS_RELIABLE,
    }


def timing(analysis: Analysis) -> dict:
    """Eerste moment op >= 70%: alleen dagen met tijdige start, niet al 70% bij de start."""
    ok_days = set(complete_days(analysis))
    pool = [o for o in analysis.offers if o.day in ok_days]
    dated = [o for o in pool if not o.at_day_start]
    bins: dict[int, int] = defaultdict(int)
    for o in dated:
        bins[(_minutes(o.first70) // BIN_MINUTES) * BIN_MINUTES] += 1
    minutes = sorted(_minutes(o.first70) for o in dated)

    def clock(m: float) -> str:
        return f"{int(m) // 60:02d}:{int(m) % 60:02d}"

    return {
        "days_used": len(ok_days),
        "days_skipped": len(analysis.days) - len(ok_days),
        "offers_dated": len(dated),
        "offers_at_start": len(pool) - len(dated),
        "bins": [(clock(b), bins[b]) for b in sorted(bins)],
        "median": clock(statistics.median(minutes)) if minutes else "",
        "p25": clock(statistics.quantiles(minutes, n=4)[0]) if len(minutes) >= 4 else "",
        "p75": clock(statistics.quantiles(minutes, n=4)[2]) if len(minutes) >= 4 else "",
    }


def _offers_on(analysis: Analysis, days: list[str]) -> list[Offer]:
    keep = set(days)
    return [o for o in analysis.offers if o.day in keep]


def by_store(analysis: Analysis) -> list[dict]:
    days = complete_days(analysis)
    pool = _offers_on(analysis, days)
    rows = []
    for store in sorted({o.store for o in pool}):
        mine = [o for o in pool if o.store == store]
        rows.append({"name": store, **_per_day(mine, days)})
    return sorted(rows, key=lambda r: (-r["suitable4_per_day"], -r["offers_per_day"], r["name"]))


def by_weekday(analysis: Analysis) -> list[dict]:
    rows = []
    for name in WEEKDAYS:
        days = [d for d in complete_days(analysis) if _weekday(d) == name]
        if days:
            rows.append({"name": name, **_per_day(_offers_on(analysis, days), days)})
    return rows


def by_week(analysis: Analysis) -> list[dict]:
    weeks: dict[str, list[str]] = defaultdict(list)
    for day in complete_days(analysis):
        iso = date.fromisoformat(day).isocalendar()
        weeks[f"{iso.year}-W{iso.week:02d}"].append(day)
    return [
        {"name": week, **_per_day(_offers_on(analysis, days), days)}
        for week, days in sorted(weeks.items())
    ]


def store_weekday(analysis: Analysis, top: int = 5) -> list[dict]:
    """Beste combinaties van winkel en weekdag op aanbiedingen voor vier personen per dag."""
    rows = []
    done = complete_days(analysis)
    for store in sorted({o.store for o in analysis.offers}):
        for name in WEEKDAYS:
            days = [d for d in done if _weekday(d) == name]
            if len(days) < MIN_DAYS_RELIABLE:
                continue
            mine = [o for o in _offers_on(analysis, days) if o.store == store]
            rows.append({"name": f"{store} op {name}", **_per_day(mine, days)})
    rows.sort(key=lambda r: (-r["suitable4_per_day"], -r["offers_per_day"], r["name"]))
    return rows[:top]


# Volgorde telt: de eerste treffer wint ("Runder hamburger" is gehakt, geen rund).
MEAT_KINDS = [
    ("kip", r"\bkip"),
    ("gehakt", r"\b(?:\w*gehakt|\w*hamburger|\w*burger)"),
    ("rund", r"\b(?:rund|biefstuk|entrecote|ribeye|bavette)"),
    ("varken", r"\b(?:varken|spek|schnitzel|braad|bacon|ham\b|karbonade)"),
    ("worst", r"\b(?:\w*worst)"),
    ("kalkoen", r"\bkalkoen"),
    ("lam", r"\blam\b|\blams"),
]
OTHER_KIND = "overig"


def meat_kind(title: str) -> str:
    """Grove indeling op titel; een aanbieding zonder herkend woord valt onder 'overig'."""
    lowered = (title or "").lower()
    for name, pattern in MEAT_KINDS:
        if re.search(pattern, lowered):
            return name
    return OTHER_KIND


def by_kind(analysis: Analysis) -> list[dict]:
    days = complete_days(analysis)
    pool = _offers_on(analysis, days)
    rows = []
    for name in [k for k, _ in MEAT_KINDS] + [OTHER_KIND]:
        mine = [o for o in pool if meat_kind(o.title) == name]
        if mine:
            rows.append({"name": name, **_per_day(mine, days)})
    return sorted(rows, key=lambda r: (-r["offers_per_day"], r["name"]))


def data_quality(analysis: Analysis) -> dict:
    unknown = [o for o in analysis.offers if o.grams_pack is None]
    days = sorted(analysis.days)
    skipped_days = [d for d in days if not analysis.days[d]["complete"]]
    return {
        "first_day": days[0] if days else "",
        "last_day": days[-1] if days else "",
        "days": len(days),
        "complete_days": len(days) - len(skipped_days),
        "incomplete_days": skipped_days,
        "offers": len(analysis.offers),
        "unknown_weight": len(unknown),
        "sources": dict(sorted(analysis.sources.items())),
        "skipped": analysis.skipped,
    }


def rolling(analysis: Analysis, window: int = 7) -> dict:
    """Laatste ``window`` kalenderdagen (t/m de laatste volledige dag) naast de ``window`` ervoor"""
    done = complete_days(analysis)
    if not done:
        return {"last": None, "prev": None, "end": ""}
    end = date.fromisoformat(done[-1])
    out: dict = {"end": done[-1]}
    for name, shift in (("last", 0), ("prev", window)):
        lo, hi = end.toordinal() - shift - window + 1, end.toordinal() - shift
        days = [d for d in done if lo <= date.fromisoformat(d).toordinal() <= hi]
        out[name] = _per_day(_offers_on(analysis, days), days)
        out[name]["from"] = date.fromordinal(lo).isoformat()
        out[name]["to"] = date.fromordinal(hi).isoformat()
    return out


def report(analysis: Analysis) -> dict:
    return {
        "quality": data_quality(analysis),
        "timing": timing(analysis),
        "stores": by_store(analysis),
        "weekdays": by_weekday(analysis),
        "weeks": by_week(analysis),
        "kinds": by_kind(analysis),
        "rolling": rolling(analysis),
        "best": store_weekday(analysis),
    }


def week_label(data: dict) -> str:
    last = data["quality"]["last_day"]
    if not last:
        return "leeg"
    iso = date.fromisoformat(last).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _fmt(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _change(new: float, old: float) -> str:
    return f"{(new / old - 1) * 100:+.0f}%" if old else "n.v.t."


def _trend_lines(rolling_data: dict) -> list[str]:
    """Laatste 7 kalenderdagen naast de 7 dagen ervoor, alleen volledige dagen."""
    last, prev = rolling_data["last"], rolling_data["prev"]
    n_last, n_prev = (last or {}).get("days", 0), (prev or {}).get("days", 0)
    if not last or not prev or last["days"] < 3 or prev["days"] < 3:
        return [
            "Te weinig volledige dagen voor een vergelijking van 7 dagen met de 7 dagen ervoor "
            f"(minimaal 3 per periode; nu {n_last} en {n_prev})."
        ]
    lines = []
    for label, row in (("Laatste 7 dagen", last), ("7 dagen ervoor", prev)):
        lines.append(
            f"{label} ({row['from']} t/m {row['to']}, {row['days']} volledige dagen): "
            f"{_fmt(row['offers_per_day'])} aanbiedingen/dag, "
            f"{_fmt(row['stock_per_day'])} stuks/dag, "
            f"{_fmt(row['suitable4_per_day'])} voor vier personen/dag."
        )
    lines.append(
        "Verschil: aanbiedingen "
        f"{_change(last['offers_per_day'], prev['offers_per_day'])}, voor vier personen "
        f"{_change(last['suitable4_per_day'], prev['suitable4_per_day'])}."
    )
    return lines


def _table(title: str, rows: list[dict], note_small: bool = True) -> list[str]:
    out = [
        f"### {title}",
        "",
        "| | dagen | aanbiedingen/dag | stuks/dag | voor 4 pers./dag | populair/dag | top/dag |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        flag = "" if r["reliable"] or not note_small else " (weinig dagen)"
        out.append(
            f"| {r['name']}{flag} | {r['days']} | {_fmt(r['offers_per_day'])} | "
            f"{_fmt(r['stock_per_day'])} | {_fmt(r['suitable4_per_day'])} | "
            f"{_fmt(r['popular_per_day'])} | {_fmt(r['top_per_day'])} |"
        )
    return out + [""]


def render_markdown(data: dict) -> str:
    q, t = data["quality"], data["timing"]
    lines = [
        f"# AH Laatste Kans weekrapport {week_label(data)}",
        "",
        f"Periode {q['first_day']} t/m {q['last_day']}: {q['days']} dagen, waarvan "
        f"{q['complete_days']} volledig (alleen die tellen mee voor gemiddelden); "
        f"{q['offers']} aanbiedingen op 70% of meer (Vlees). Voor vier personen telt een "
        f"aanbieding vanaf {FOUR_PERSON_GRAMS:.0f} g in totaal (gewicht per pak maal voorraad).",
        "",
        "## Trend",
        "",
        *_trend_lines(data["rolling"]),
        "",
        "## Op welk moment gaan aanbiedingen naar 70%?",
        "",
        f"Gebaseerd op {t['days_used']} volledige dagen ({t['days_skipped']} dagen "
        f"overgeslagen). {t['offers_dated']} aanbiedingen met een bekend tijdstip; "
        f"{t['offers_at_start']} stonden al op 70% bij de eerste scan en zijn niet te dateren.",
    ]
    if t["median"]:
        lines.append(
            f"Mediaan {t['median']}"
            + (f" (25%: {t['p25']}, 75%: {t['p75']})." if t["p25"] else ".")
        )
    lines += [
        "",
        "| vanaf | aanbiedingen |",
        "|---|---|",
        *[f"| {b} | {n} |" for b, n in t["bins"]],
        "",
    ]
    lines += _table("Per filiaal (gesorteerd op aanbiedingen voor vier personen)", data["stores"])
    lines += _table("Per soort vlees (grove indeling op titel)", data["kinds"])
    lines += _table("Per weekdag", data["weekdays"])
    lines += _table("Beste combinaties filiaal en weekdag (minimaal 4 dagen)", data["best"], False)
    lines += _table("Per week", data["weeks"])
    lines += [
        "## Datakwaliteit",
        "",
        f"- Bronnen (scanrijen): {q['sources']}; overgeslagen regels: {q['skipped']}.",
        f"- Onvolledige dagen (niet meegeteld): {len(q['incomplete_days'])}"
        + (f", laatste: {', '.join(q['incomplete_days'][-5:])}." if q["incomplete_days"] else "."),
        f"- Aanbiedingen zonder bekend gewicht (tellen niet mee voor vier personen): "
        f"{q['unknown_weight']}.",
        "- Kleine groepen (minder dan 4 dagen) zijn gemarkeerd; trek er geen conclusies uit.",
        "- Dit zijn gemeten patronen, geen verklaringen.",
    ]
    return "\n".join(lines) + "\n"


CELL_STYLE = "padding:2px 8px;border-bottom:1px solid #e4e7ec;text-align:left"
TABLE_STYLE = "border-collapse:collapse;margin:6px 0"


def _html_row(cells: list[str], tag: str) -> str:
    inner = "".join(f'<{tag} style="{CELL_STYLE}">{escape(c)}</{tag}>' for c in cells)
    return f"<tr>{inner}</tr>"


def _html_table(rows: list[str]) -> str:
    return f'<table style="{TABLE_STYLE}">{"".join(rows)}</table>'


def render_html(data: dict) -> str:
    """Eenvoudige HTML-versie (koppen, lijsten en tabellen) van het markdown-rapport."""
    out = ['<div style="font-family:-apple-system,Segoe UI,Arial,sans-serif;max-width:720px">']
    rows: list[str] = []
    for line in render_markdown(data).splitlines():
        if line.startswith("|"):
            if set(line.replace("|", "").strip()) <= {"-"}:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows.append(_html_row(cells, "th" if not rows else "td"))
            continue
        if rows:
            out.append(_html_table(rows))
            rows = []
        if line.startswith("# "):
            out.append(f"<h2>{escape(line[2:])}</h2>")
        elif line.startswith("## "):
            out.append(f'<h3 style="margin-top:18px">{escape(line[3:])}</h3>')
        elif line.startswith("### "):
            out.append(f'<h4 style="margin:12px 0 4px">{escape(line[4:])}</h4>')
        elif line.startswith("- "):
            out.append(f"<div>• {escape(line[2:])}</div>")
        elif line:
            out.append(f"<p>{escape(line)}</p>")
    if rows:
        out.append(_html_table(rows))
    out.append("</div>")
    return "".join(out)
