import json
from datetime import date, timedelta

import pytest

from ah_scanner import analyze


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ("500 g", 500.0),
        ("ca. 140 g", 140.0),
        ("1 kg", 1000.0),
        ("ca. 1,2 kg", 1200.0),
        ("ca. 1375 g", 1375.0),
        ("2 x 125 g", 250.0),
        ("4 stuks", None),
        ("per stuk", None),
        ("", None),
        (None, None),
    ],
)
def test_grams_of(size, expected):
    assert analyze.grams_of(size) == expected


def item(pid, title="Kip", size="300 g", pct=70.0, stock=1.0, expires="2026-11-16"):
    return {
        "product_id": pid, "title": title, "brand": "AH", "size": size, "category": "Vlees",
        "discount_pct": pct, "stock": stock, "price_was": "5.00", "price_now": "1.50",
        "expires": expires,
    }  # fmt: skip


def scan(day, slot, items, store_id=1463, store="AH Test"):
    stamp = f"{day}T{slot}:00+01:00"
    meat70 = [i for i in items if i["discount_pct"] >= 70]
    return {
        "scheduled_at": stamp, "started_at": stamp, "completed_at": stamp, "delay_seconds": 40,
        "late": False, "status": "OK", "valid": True,
        "stores": [{
            "store_id": store_id, "store": store, "fetched": True, "total_items": 9,
            "meat_items": items, "meat70": meat70, "error": "",
        }],
    }  # fmt: skip


def write_day(root, day, records):
    path = root / "scans" / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def full_day(root, day, hits, store_id=1463, store="AH Test"):
    """Volledige dag met scans op 17:30 en 22:30; ``hits`` = {slot: [items op 70%]}."""
    slots = sorted({"17:30", "22:30", *hits})
    records = [scan(day, s, hits.get(s, []), store_id, store) for s in slots]
    write_day(root, day, records)


def test_offer_eerste_moment_stock_en_vier_personen(tmp_path):
    day = "2026-11-16"
    low = [item(1, size="250 g", stock=1.0, pct=40.0)]
    hit1 = [item(1, size="250 g", stock=1.0)]  # 250 g totaal: niet voor 4
    hit2 = [item(1, size="250 g", stock=3.0)]  # later meer voorraad: 750 g
    write_day(
        tmp_path, day,
        [scan(day, "17:30", low), scan(day, "19:00", hit1), scan(day, "19:05", hit2),
         scan(day, "22:30", [])],
    )  # fmt: skip
    a = analyze.build(tmp_path)
    assert len(a.offers) == 1
    offer = a.offers[0]
    assert offer.first70 == "19:00" and offer.stock == 3.0 and not offer.at_day_start
    assert offer.total_grams == 750.0 and offer.suitable4 is True


def test_vier_personen_grens_is_inclusief_en_onbekend_gewicht_telt_niet_mee(tmp_path):
    day = "2026-11-16"
    exact = item(1, size="500 g", stock=1.0)
    below = item(2, size="499 g", stock=1.0)
    unknown = item(3, size="per stuk", stock=9.0)
    full_day(tmp_path, day, {"19:00": [exact, below, unknown]})
    a = analyze.build(tmp_path)
    by_id = {o.product_id: o for o in a.offers}
    assert by_id["1"].suitable4 is True and by_id["2"].suitable4 is False
    assert by_id["3"].suitable4 is None and analyze.data_quality(a)["unknown_weight"] == 1


def test_al_70_bij_eerste_scan_wordt_niet_gedateerd(tmp_path):
    day = "2026-11-16"
    full_day(tmp_path, day, {"17:30": [item(1)], "19:00": [item(2)]})
    t = analyze.timing(analyze.build(tmp_path))
    assert t["offers_at_start"] == 1 and t["offers_dated"] == 1
    assert t["bins"] == [("19:00", 1)] and t["median"] == "19:00"


def test_onvolledige_dagen_tellen_niet_mee_voor_gemiddelden_of_tijdstip(tmp_path):
    full_day(tmp_path, "2026-11-16", {"19:00": [item(1)]})
    write_day(
        tmp_path,
        "2026-11-15",
        [scan("2026-11-15", "20:00", [item(2)]), scan("2026-11-15", "22:30", [item(2)])],
    )  # late start
    write_day(
        tmp_path,
        "2026-11-14",
        [scan("2026-11-14", "17:30", [item(3)]), scan("2026-11-14", "20:00", [item(3)])],
    )  # vroeg einde
    a = analyze.build(tmp_path)
    assert analyze.complete_days(a) == ["2026-11-16"]
    q = analyze.data_quality(a)
    assert q["days"] == 3 and q["complete_days"] == 1
    assert q["incomplete_days"] == ["2026-11-14", "2026-11-15"]
    assert analyze.by_store(a)[0]["offers"] == 1  # alleen de volledige dag
    assert analyze.timing(a)["days_used"] == 1 and analyze.timing(a)["days_skipped"] == 2


def test_per_filiaal_gesorteerd_op_vier_personen_en_weinig_dagen_vlag(tmp_path):
    day = "2026-11-16"
    full_day(tmp_path, day, {"19:00": [item(1, size="600 g")]}, 1463, "Winkel A")
    # tweede winkel in dezelfde scans: voeg toe aan hetzelfde bestand
    path = tmp_path / "scans" / f"{day}.jsonl"
    extra = scan(day, "19:00", [item(5, size="100 g"), item(6, size="100 g")], 1348, "Winkel B")
    path.write_text(path.read_text() + json.dumps(extra) + "\n", encoding="utf-8")
    rows = analyze.by_store(analyze.build(tmp_path))
    assert [r["name"] for r in rows] == ["Winkel A", "Winkel B"]  # A: 1 voor vier; B: 2 maar klein
    assert rows[0]["suitable4"] == 1 and rows[1]["offers"] == 2 and rows[1]["suitable4"] == 0
    assert rows[0]["reliable"] is False  # 1 dag < 4


def test_per_weekdag_en_beste_combinaties_vereisen_minimaal_vier_dagen(tmp_path):
    monday = date(2026, 11, 2)  # maandag
    for week in range(4):
        day = (monday + timedelta(days=7 * week)).isoformat()
        full_day(tmp_path, day, {"19:00": [item(week, size="800 g")]})
    full_day(tmp_path, "2026-11-03", {"19:00": [item(99, size="800 g")]})  # 1 dinsdag
    a = analyze.build(tmp_path)
    weekdays = {r["name"]: r for r in analyze.by_weekday(a)}
    assert weekdays["maandag"]["days"] == 4 and weekdays["maandag"]["reliable"] is True
    assert weekdays["dinsdag"]["days"] == 1 and weekdays["dinsdag"]["reliable"] is False
    best = analyze.store_weekday(a)
    assert [r["name"] for r in best] == ["AH Test op maandag"] and best[0][
        "suitable4_per_day"
    ] == 1.0


def test_rollend_venster_vergelijkt_zeven_dagen_en_meldt_te_weinig_data(tmp_path):
    for n in range(1, 8):  # 1 t/m 7 november: laatste week, 1 offer per dag
        full_day(tmp_path, f"2026-11-{n:02d}", {"19:00": [item(n, size="600 g")]})
    for n in range(25, 32):  # 25 t/m 31 oktober: week ervoor, 2 offers per dag
        day = f"2026-10-{n}"
        full_day(tmp_path, day, {"19:00": [item(n, size="600 g"), item(n + 100, size="600 g")]})
    a = analyze.build(tmp_path)
    roll = analyze.rolling(a)
    assert roll["end"] == "2026-11-07"
    assert roll["last"]["days"] == 7 and roll["prev"]["days"] == 7
    assert roll["last"]["offers_per_day"] == 1.0 and roll["prev"]["offers_per_day"] == 2.0
    text = "\n".join(analyze._trend_lines(roll))
    assert "Laatste 7 dagen" in text and "aanbiedingen -50%" in text
    few = analyze.rolling(analyze.build(_one_day(tmp_path / "x")))
    assert "Te weinig volledige dagen" in "\n".join(analyze._trend_lines(few))


def _one_day(root):
    full_day(root, "2026-11-16", {"19:00": [item(1)]})
    return root


def test_rapport_markdown_en_html_bevatten_alle_onderdelen(tmp_path):
    full_day(tmp_path, "2026-11-16", {"19:00": [item(1, "<b>Kip</b>", size="600 g")]}, store="A&B")
    data = analyze.report(analyze.build(tmp_path))
    md = analyze.render_markdown(data)
    for needle in (
        "weekrapport 2026-W47",
        "## Trend",
        "Op welk moment",
        "Per filiaal",
        "Per soort vlees",
        "Per weekdag",
        "Per week",
        "## Datakwaliteit",
        "500 g in totaal",
    ):
        assert needle in md
    html = analyze.render_html(data)
    assert "<h2>" in html and "<table" in html and "A&amp;B" in html and "<th" in html
    assert "<script" not in html


def test_leeg_en_rommel_geeft_een_rapport_zonder_fout(tmp_path):
    data = analyze.report(analyze.build(tmp_path))
    assert analyze.week_label(data) == "leeg"
    assert "weekrapport leeg" in analyze.render_markdown(data)
    (tmp_path / "scans").mkdir()
    (tmp_path / "scans" / "2026-11-16.jsonl").write_text("{kapot\n", encoding="utf-8")
    assert analyze.data_quality(analyze.build(tmp_path))["skipped"] == 1


class Mailer:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def __call__(self, payload):
        self.sent.append(payload)
        return self.ok


def test_cli_report_schrijft_bestand_en_mailt(tmp_path, monkeypatch, capsys):
    from ah_scanner import cli

    full_day(tmp_path / "data", "2026-11-16", {"19:00": [item(1, size="600 g")]})
    monkeypatch.setenv("AH_MAIL_FROM", "a@x")
    monkeypatch.setenv("AH_MAIL_TO", "b@x")
    mailer = Mailer()
    code = cli.report(tmp_path / "data", tmp_path / "out", True, mailer)
    assert code == 0 and (tmp_path / "out" / "2026-W47.md").exists()
    assert mailer.sent[0]["subject"] == "AH Laatste Kans weekrapport 2026-W47"
    assert mailer.sent[0]["to"] == ["b@x"] and "<table" in mailer.sent[0]["html"]
    assert "REPORT_MAIL sent" in capsys.readouterr().out


def test_cli_report_zonder_mail_en_met_mailfout_of_ontbrekende_config(tmp_path, monkeypatch):
    from ah_scanner import cli

    full_day(tmp_path / "data", "2026-11-16", {"19:00": [item(1)]})
    assert cli.report(tmp_path / "data", tmp_path / "o1", False) == 0
    monkeypatch.setenv("AH_MAIL_FROM", "a@x")
    monkeypatch.setenv("AH_MAIL_TO", "b@x")
    assert (
        cli.report(tmp_path / "data", tmp_path / "o2", True, Mailer(False))
        == cli.EXIT_NOTIFY_FAILED
    )
    for var in ("RESEND_API_KEY", "AH_MAIL_FROM", "AH_MAIL_TO"):
        monkeypatch.delenv(var, raising=False)
    assert cli.report(tmp_path / "data", tmp_path / "o3", True) == cli.EXIT_NOTIFY_FAILED


def test_cli_main_report_commando(tmp_path, capsys):
    from ah_scanner import cli

    full_day(tmp_path / "data", "2026-11-16", {"19:00": [item(1)]})
    argv = ["report", "--data-root", str(tmp_path / "data"), "--out", str(tmp_path / "out")]
    assert cli.main(argv) == 0
    assert "REPORT week=2026-W47 days=1 offers=1" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("AH Scharrel kipfilet", "kip"),
        ("AH Runder hamburger 4 stuks", "gehakt"),
        ("AH Rundergehakt", "gehakt"),
        ("AH Biefstuk", "rund"),
        ("Varkenshaas", "varken"),
        ("Gelderse rookworst", "worst"),
        ("Kalkoenfilet", "kalkoen"),
        ("Salami", "overig"),
        ("", "overig"),
    ],
)
def test_meat_kind_grove_indeling_op_titel(title, expected):
    assert analyze.meat_kind(title) == expected


def test_per_soort_vlees_telt_per_dag_en_sorteert_op_aantal(tmp_path):
    hits = [item(1, "Kipfilet"), item(2, "Kipdij"), item(3, "Rundergehakt"), item(4, "Salami")]
    full_day(tmp_path, "2026-11-16", {"19:00": hits})
    rows = analyze.by_kind(analyze.build(tmp_path))
    assert [(r["name"], r["offers"]) for r in rows] == [("kip", 2), ("gehakt", 1), ("overig", 1)]
