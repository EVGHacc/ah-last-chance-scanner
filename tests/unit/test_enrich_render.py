import json

import pytest

from ah_scanner import enrich, render
from ah_scanner.enrich import JA, NEE, ONBEKEND, Enrichment
from ah_scanner.models import OK, Item, ScanResult, StoreResult
from ah_scanner.offers import Offer

# Let op: dit zijn zelf bedachte voorbeeldzinnen, geen geverifieerde AH-teksten.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bewaren in de koelkast. Op de dag van aankoop invriezen.", JA),
        ("Bewaren in de koelkast (max 4 °C). Invriezen op de dag van aankoop.", JA),
        ("Bewaren: Op de dag van aankoop in te vriezen.", JA),
        ("Niet geschikt om in te vriezen.", NEE),
        ("Dit product niet invriezen.", NEE),
        ("Op de dag van aankoop invriezen. Ontdooid product niet opnieuw invriezen.", JA),
        ("Ontdooid product niet opnieuw invriezen.", ONBEKEND),
        ("Bewaren in de koelkast.", ONBEKEND),
        ("", ONBEKEND),
        ("Invriezen mogelijk. Niet geschikt om in te vriezen.", NEE),
    ],
)
def test_classify_freeze(text, expected):
    assert enrich.classify_freeze(text) == expected


def make_query(image=None, storage=None, errors=None, calls=None):
    def query(text, variables):
        if calls is not None:
            calls.append(text)
        pid = variables["productId"]
        if errors and ("part" in errors) and errors["part"] in text:
            return 200, {"errors": [{"message": errors["msg"]}]}
        if "imagePack" in text:
            pack = [{"medium": {"url": image}}] if image else []
            return 200, {"data": {"product": {"id": pid, "imagePack": pack}}}
        return 200, {"data": {"product": {"id": pid, "tradeItem": {"storage": storage}}}}

    return query


def item(pid=1, title="Gehakt <b>"):
    return Item(pid, title, "AH", "500 g", "Vlees", 70.0, 3, "5.00", "1.50", "2026-11-16")


def test_enrich_haalt_foto_en_bewaartekst_op_en_cachet(tmp_path):
    calls: list[str] = []
    storage = {"instructions": ["Op de dag van aankoop invriezen."], "lifeSpan": ["Tot 16-11"]}
    query = make_query("https://static.ah.nl/x.jpg", storage, calls=calls)
    first = enrich.enrich_items([item(1), item(1)], query, tmp_path)
    assert first[1] == Enrichment(
        "https://static.ah.nl/x.jpg", "Op de dag van aankoop invriezen.", "Tot 16-11"
    )
    assert first[1].freeze == JA and len(calls) == 2
    enrich.enrich_items([item(1)], query, tmp_path)
    assert len(calls) == 2  # tweede keer uit de cache
    assert json.loads((tmp_path / "product_info.json").read_text())["1"]["image"]


def test_onveilige_foto_url_wordt_genegeerd(tmp_path):
    out = enrich.enrich_items([item()], make_query("http://evil/x.jpg", {}), tmp_path)
    assert out[1].image_url == ""


def test_storage_als_tekst_of_onbekend_type(tmp_path):
    text = enrich.enrich_items(
        [item(1)], make_query(None, {"instructions": "Invriezen."}), tmp_path
    )
    assert text[1].storage == "Invriezen."
    odd = enrich.enrich_items([item(2)], make_query(None, {"instructions": [{"a": 1}]}), tmp_path)
    assert odd[2].storage == ""


def test_graphql_fout_wordt_gelogd_niet_gecachet_en_blokkeert_niet(tmp_path, capsys):
    query = make_query(
        "https://static.ah.nl/x.jpg", None, {"part": "tradeItem", "msg": "boom\n" * 80}
    )
    out = enrich.enrich_items([item(1)], query, tmp_path)
    assert out[1].image_url and out[1].storage == ""
    log = capsys.readouterr().out
    assert "ENRICH_ERROR product=1 part=storage" in log and len(log) < 300
    cached = json.loads((tmp_path / "product_info.json").read_text())["1"]
    assert "storage" not in cached and "image" in cached  # fout wordt opnieuw geprobeerd


def test_cap_en_netwerkfout(tmp_path):
    out = enrich.enrich_items([item(i) for i in range(1, 6)], lambda q, v: (0, {}), tmp_path, cap=3)
    assert set(out) == {1, 2, 3} and not (tmp_path / "product_info.json").exists()


def scan(valid=True, late=False):
    store = StoreResult(1463, "AH Test", valid, 1, (item(1),), (item(1),))
    return ScanResult("s", "t", "c", 0, late, OK if valid else "INCOMPLETE", (store,))


def offer(pid=1, **kw):
    return Offer(1463, "AH Test", item(pid), f"1463|{pid}|2026-11-16", **kw)


def test_html_kaart_heeft_foto_prijs_invriesbaar_en_ontsnapt_html():
    info = {1: Enrichment("https://static.ah.nl/x.jpg", "Invriezen op de dag van aankoop.", "")}
    html = render.render_html([offer()], [], [], [], scan(), info)
    assert '<img src="https://static.ah.nl/x.jpg"' in html
    assert "€ 1,50" in html and "€ 5,00" in html and "-70%" in html
    assert "Invriesbaar:" in html and ">Ja<" in html and "16-11-2026" in html
    assert "Gehakt &lt;b&gt;" in html and "<b>Gehakt" not in html


def test_html_zonder_verrijking_toont_onbekend_en_plaatshouder():
    html = render.render_html([offer()], [], [], [], scan(valid=False, late=True), {})
    assert "Onbekend" in html and "<img" not in html and "Late scan" in html


def test_nieuw_label_en_laatst_bekend_in_html_en_tekst():
    new, old = offer(1, is_new=True), offer(2, stale=True)
    html = render.render_html([new, old], [new], [], ["AH Test"], scan(), {})
    assert html.count("NIEUW") == 1 and "Laatst bekende stand" in html
    text = render.render_text([new, old], [new], [], ["AH Test"], scan(), {})
    assert "[NIEUW]" in text and "(laatst bekend)" in text and "niet gelezen" in text


def test_tekstversie_bevat_invriesbaar_en_bewaren():
    info = {1: Enrichment("", "Niet geschikt om in te vriezen.", "")}
    text = render.render_text([offer()], [], [], [], scan(), info)
    assert "invriesbaar: Nee" in text and "Bewaren: Niet geschikt" in text


def scan_on(day_iso):
    store = StoreResult(1463, "AH Test", True, 1, (item(1),), (item(1),))
    stamp = f"{day_iso}T17:30:00+01:00"
    return ScanResult(stamp, stamp, stamp, 0, False, OK, (store,))


def with_expiry(expires):
    return Offer(
        1463, "AH Test", Item(1, "Kip", "AH", "300 g", "Vlees", 70.0, 1, "5", "1.5", expires), "k"
    )


def test_alleen_vandaag_label_bij_einddatum_vandaag():
    sc = scan_on("2026-11-16")
    html = render.render_html([with_expiry("2026-11-16")], [], [], [], sc, {})
    assert "ALLEEN VANDAAG" in html and "Tot 16-11-2026" not in html
    text = render.render_text([with_expiry("2026-11-16")], [], [], [], sc, {})
    assert "alleen vandaag" in text


def test_latere_einddatum_toont_de_datum_zonder_vandaag_label():
    sc = scan_on("2026-11-16")
    html = render.render_html([with_expiry("2026-11-19")], [], [], [], sc, {})
    assert "Tot 19-11-2026" in html and "ALLEEN VANDAAG" not in html
    assert "tot 19-11-2026" in render.render_text([with_expiry("2026-11-19")], [], [], [], sc, {})


def test_validity_en_scan_day_randgevallen():
    sc = scan_on("2026-11-16")
    assert render.scan_day(sc) == "2026-11-16"
    assert render.scan_day(scan()) is None  # onleesbaar scanmoment
    assert render.validity(with_expiry("2026-11-16").item, None) == ("Tot 16-11-2026", False)
    assert render.validity(with_expiry(None).item, "2026-11-16") == ("Tot -", False)


# Echte bewaarteksten van AH, 16 november 2026 (alle 9 unieke teksten uit product_info.json).
JA_TEXT = (
    "Geschikt om thuis in te vriezen op de dag van aankoop. Binnen 3 maanden gebruiken. "
    "Voor gebruik ontdooien. Te gebruiken tot en met: zie bovenzijde, mits gekoeld bewaard "
    "(max. 4°C). Gebruik voor of op de vermelde datum. Niet gebruiken na deze datum."
)
NEE_TEXT = (
    "Niet geschikt om thuis in te vriezen. Te gebruiken tot en met: zie bovenzijde, mits gekoeld "
    "bewaard (max. 4°C). Gebruik voor of op de vermelde datum. Niet gebruiken na deze datum."
)
REAL_TEXTS = [
    (JA_TEXT, JA),
    (JA_TEXT.replace("Niet gebruiken na deze datum.", "Niet gebruiken na deze datum"), JA),
    (
        "Geschikt om thuis in te vriezen op de dag van aankoop. Binnen 3 maanden gebruiken. "
        "Voor gebruik ontdooien. Te gebruiken tot en met: zie bovenzijde, mits gekoeld bewaard "
        "(max. 4°C). Te consumeren binnen 3 dagen na openen, echter nooit later dan de vermelde "
        "datum.",
        JA,
    ),
    (NEE_TEXT, NEE),
    (NEE_TEXT.replace("bovenzijde", "voorzijde"), NEE),
    (
        "Koel bewaren max. 7°C.\nTenminste houdbaar tot (mits ongeopend en gekoeld): "
        "zie voorzijde.",
        ONBEKEND,
    ),
    (
        "Te gebruiken tot;\nzie bovenzijde mits gekoeld bewaard (max 4°C)\n"
        "Na openen beperkt houdbaar.",
        ONBEKEND,
    ),
    (
        "Te gebruiken tot en met: zie bovenzijde, mits gekoeld bewaard (max. 4°C). Gebruik voor of "
        "op de vermelde datum. Niet gebruiken na deze datum.",
        ONBEKEND,
    ),
    (
        "Te gebruiken tot en met: zie voorzijde, mits gekoeld bewaard (max. 7°C). Gebruik voor of "
        "op de vermelde datum. Niet gebruiken na deze datum. Na openen beperkt houdbaar.",
        ONBEKEND,
    ),
]


@pytest.mark.parametrize(("text", "expected"), REAL_TEXTS)
def test_classify_freeze_echte_ah_teksten(text, expected):
    assert enrich.classify_freeze(text) == expected


def test_echte_tekst_zonder_invries_zin_blijft_onbekend_ondanks_niet_in_andere_zinnen():
    # "Niet gebruiken na deze datum." bevat 'niet' maar niets over invriezen.
    assert "Niet gebruiken" in REAL_TEXTS[7][0]
    assert enrich.classify_freeze(REAL_TEXTS[7][0]) == ONBEKEND


def test_nieuw_banner_staat_boven_de_kaart_en_alleen_bij_nieuwe_aanbiedingen():
    new, old = offer(1, is_new=True), offer(2)
    html = render.render_html([new, old], [new], [], [], scan(), {})
    banner = 'colspan="2" style="background:#1a7f37'
    assert html.count(banner) == 1
    assert html.index(banner) < html.index("<img") if "<img" in html else True
    only_old = render.render_html([old], [], [], [], scan(), {})
    assert "NIEUW" not in only_old


def _gezin_item(title, size, stock):
    return Item(1, title, "AH", size, "Vlees", 70.0, stock, "5.00", "1.50", "2026-11-16")


def _gezin_offer(title, size, stock):
    return Offer(1463, "AH Test", _gezin_item(title, size, stock), "k")


def test_mail_toont_topaanbieding_en_totaalgewicht_voor_gezin():
    top = _gezin_offer("Kipfilet", "250 g", 2)
    plain = _gezin_offer("Varkenshaas", "250 g", 1)
    html = render.render_html([top, plain], [], [], [], scan(), {})
    assert html.count("TOPAANBIEDING VOOR 4") == 1 and "2 × 250 g = 500 g" in html
    assert "genoeg voor 4 personen" in html and "te weinig voor 4 personen" in html
    text = render.render_text([top, plain], [], [], [], scan(), {})
    assert "[TOP] " in text and "Gezin van 4: 500 g" not in text and "2 × 250 g = 500 g" in text


def test_mail_populair_zonder_genoeg_en_onbekend_gewicht():
    small = _gezin_offer("Gehakt", "250 g", 1)
    unknown = _gezin_offer("Gehakt", "per stuk", 1)
    html = render.render_html([small, unknown], [], [], [], scan(), {})
    assert html.count(">POPULAIR<") == 2 and "TOPAANBIEDING" not in html
    assert html.count("Gezin van 4:") == 1  # onbekend gewicht: geen regel
    text = render.render_text([small, unknown], [], [], [], scan(), {})
    assert text.count("[POPULAIR]") == 2
