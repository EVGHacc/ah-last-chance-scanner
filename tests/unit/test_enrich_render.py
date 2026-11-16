import json

import pytest

from ah_scanner import enrich, render
from ah_scanner.enrich import JA, NEE, ONBEKEND, Enrichment
from ah_scanner.models import OK, Item, ScanResult

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
    return ScanResult("s", "t", "c", 0, late, OK if valid else "INCOMPLETE")


def test_html_kaart_heeft_foto_prijs_invriesbaar_en_ontsnapt_html():
    info = {1: Enrichment("https://static.ah.nl/x.jpg", "Invriezen op de dag van aankoop.", "")}
    html = render.render_html([("AH Test", item(1), "k")], scan(), info)
    assert '<img src="https://static.ah.nl/x.jpg"' in html
    assert "€ 1,50" in html and "€ 5,00" in html and "-70%" in html
    assert "Invriesbaar:" in html and ">Ja<" in html and "16-11-2026" in html
    assert "Gehakt &lt;b&gt;" in html and "<b>Gehakt" not in html


def test_html_zonder_verrijking_toont_onbekend_en_plaatshouder():
    html = render.render_html([("AH Test", item(1), "k")], scan(valid=False, late=True), {})
    assert "Onbekend" in html and "<img" not in html and "INCOMPLETE" in html


def test_tekstversie_bevat_invriesbaar_en_bewaren():
    info = {1: Enrichment("", "Niet geschikt om in te vriezen.", "")}
    text = render.render_text([("AH Test", item(1), "k")], scan(), info)
    assert "invriesbaar: Nee" in text and "Bewaren: Niet geschikt" in text
