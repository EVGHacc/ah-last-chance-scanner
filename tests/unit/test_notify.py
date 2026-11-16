from datetime import date

from ah_scanner import cli, notify
from ah_scanner.enrich import Enrichment
from ah_scanner.models import INCOMPLETE, OK, STORES, Item, ScanResult, StoreResult

from .test_client import ok_payload
from .test_filters_slots import row
from .test_storage_scan import SCHED, env, good_post  # noqa: F401

DAY = date(2026, 11, 16)


def item(pid=1, title="Gehakt", pct=70.0, expires="2026-11-16"):
    return Item(pid, title, "AH", "500 g", "Vlees", pct, 2, "5.00", "1.00", expires)


def scan(by_store=None, status=OK, unread=()):
    by_store = by_store or {}
    stores = tuple(
        StoreResult(
            sid,
            name,
            sid not in unread,
            len(by_store.get(sid, ())),
            tuple(by_store.get(sid, ())),
            tuple(by_store.get(sid, ())),
        )
        for sid, name in STORES
    )
    return ScanResult(
        SCHED.isoformat(), SCHED.isoformat(), SCHED.isoformat(), 0, False, status, stores
    )


class Mailer:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def __call__(self, payload):
        self.sent.append(payload)
        return self.ok


def run(sc, root, mailer, enrich=None):
    return notify.notify(sc, DAY, root, mailer, "a@x", "b@x", enrich)


def test_geen_mail_zonder_aanbod(tmp_path):
    m = Mailer()
    assert run(scan(), tmp_path, m) == "none" and not m.sent


def test_eerste_aanbod_geeft_mail_met_alle_winkels_gegroepeerd(tmp_path):
    m = Mailer()
    sc = scan({1463: [item(1, "Kip")], 1348: [item(2, "Rund")]})
    assert run(sc, tmp_path, m) == "sent"
    text, html = m.sent[0]["text"], m.sent[0]["html"]
    assert text.index("AH Blekersvaartweg (1)") < text.index("AH Zandvoortselaan (1)")
    assert "AH Westergracht (0)" in text and "Geen 70%-aanbiedingen" in text
    assert "NIEUW" in html and "<h3" in html
    assert m.sent[0]["subject"] == "AH Laatste Kans: 2 aanbiedingen Vlees >= 70% (+2 / -0)"


def test_ongewijzigde_stand_geeft_geen_tweede_mail(tmp_path):
    m = Mailer()
    sc = scan({1463: [item(1)]})
    run(sc, tmp_path, m)
    assert run(sc, tmp_path, m) == "none" and len(m.sent) == 1


def test_aanbieding_erbij_geeft_mail_met_alle_aanbiedingen_en_nieuw_label(tmp_path):
    m = Mailer()
    run(scan({1463: [item(1, "Kip")]}), tmp_path, m)
    run(scan({1463: [item(1, "Kip"), item(2, "Worst")]}), tmp_path, m)
    second = m.sent[1]
    assert "Kip" in second["text"] and "Worst" in second["text"]  # alles, niet alleen het nieuwe
    assert second["text"].count("[NIEUW]") == 1
    assert second["subject"].endswith("(+1 / -0)")


def test_aanbieding_eraf_geeft_mail_met_verdwenen_lijst(tmp_path):
    m = Mailer()
    run(scan({1463: [item(1, "Kip"), item(2, "Worst")]}), tmp_path, m)
    assert run(scan({1463: [item(1, "Kip")]}), tmp_path, m) == "sent"
    second = m.sent[1]
    assert "Verdwenen sinds de vorige mail" in second["html"] and "Worst" in second["html"]
    assert second["subject"].endswith("(+0 / -1)") and "[NIEUW]" not in second["text"]


def test_alle_aanbod_verdwenen_geeft_mail_met_nul(tmp_path):
    m = Mailer()
    run(scan({1463: [item(1)]}), tmp_path, m)
    assert run(scan(), tmp_path, m) == "sent"
    assert "Nu 0 aanbiedingen" in m.sent[1]["text"]


def test_zelfde_product_andere_winkel_is_een_wijziging(tmp_path):
    m = Mailer()
    run(scan({1463: [item(1)]}), tmp_path, m)
    assert run(scan({1463: [item(1)], 1348: [item(1)]}), tmp_path, m) == "sent"


def test_nieuwe_dag_begint_zonder_vorige_stand(tmp_path):
    m = Mailer()
    run(scan({1463: [item(1)]}), tmp_path, m)
    next_day = date(2026, 11, 17)
    assert notify.notify(scan({1463: [item(1)]}), next_day, tmp_path, m, "a@x", "b@x") == "sent"
    assert "Verdwenen" not in m.sent[1]["html"]  # gisteren telt niet als 'eraf'


def test_mislukte_verzending_bewaart_niets_en_probeert_opnieuw(tmp_path):
    sc = scan({1463: [item(1)]})
    assert run(sc, tmp_path, Mailer(False)) == "failed"
    assert run(sc, tmp_path, Mailer(True)) == "sent"


def test_niet_gelezen_winkel_is_geen_verdwenen_aanbod_maar_laatst_bekend(tmp_path):
    m = Mailer()
    run(scan({1348: [item(7, "Rund")], 1463: [item(1, "Kip")]}), tmp_path, m)
    partial = scan({1463: [item(1, "Kip"), item(2, "Worst")]}, status=INCOMPLETE, unread=(1348,))
    assert run(partial, tmp_path, m) == "sent"
    second = m.sent[1]
    assert "Rund" in second["text"] and "(laatst bekend)" in second["text"]
    assert "niet gelezen" in second["text"] and second["subject"].endswith("(+1 / -0)")
    # alleen een niet-gelezen winkel zonder verdere wijziging: geen mail
    assert (
        run(scan({1463: [item(1), item(2)]}, status=INCOMPLETE, unread=(1348,)), tmp_path, m)
        == "none"
    )


def test_scan_zonder_enige_gelezen_winkel_geeft_geen_mail(tmp_path):
    m = Mailer()
    run(scan({1463: [item(1)]}), tmp_path, m)
    failed = scan(status="FAILED", unread=tuple(sid for sid, _ in STORES))
    assert run(failed, tmp_path, m) == "none" and len(m.sent) == 1


def test_verrijking_voor_alle_getoonde_producten_en_fout_blokkeert_niet(tmp_path):
    m, asked = Mailer(), []

    def enrich_ok(items):
        asked.append([i.product_id for i in items])
        return {1: Enrichment("https://static.ah.nl/a.jpg", "Invriezen.", "")}

    assert run(scan({1463: [item(1), item(2)]}), tmp_path, m, enrich_ok) == "sent"
    assert asked == [[1, 2]]
    assert "<img" in m.sent[0]["html"] and "invriesbaar: Ja" in m.sent[0]["text"]

    def enrich_boom(items):
        raise RuntimeError("stuk")

    assert run(scan({1463: [item(3)]}), tmp_path, m, enrich_boom) == "sent"
    assert "Onbekend" in m.sent[1]["html"]


def test_html_escapet_titels(tmp_path):
    m = Mailer()
    run(scan({1463: [item(1, "<script>x</script>")]}), tmp_path, m)
    assert "<script>" not in m.sent[0]["html"] and "&lt;script&gt;" in m.sent[0]["html"]


def test_cli_scan_mailt_en_stuurt_geen_dubbele_mail(env):  # noqa: F811
    m = Mailer()
    kw = dict(
        post=good_post,
        graphql=lambda s, a: ok_payload(row(pct=90)),
        now=lambda: SCHED,
        send=m,
        query=lambda q, v: (200, {"data": {"product": {"imagePack": []}}}),
    )
    args = (SCHED.isoformat(), env / "s.enc", env / "d")
    assert cli.scan(*args, **kw) == 0
    assert len(m.sent) == 1
    assert cli.scan(*args, **kw) == 0 and len(m.sent) == 1


def test_cli_mailfout_geeft_exit_5(env):  # noqa: F811
    code = cli.scan(
        SCHED.isoformat(),
        env / "s.enc",
        env / "d",
        good_post,
        lambda s, a: ok_payload(row(pct=90)),
        lambda: SCHED,
        Mailer(False),
        lambda q, v: (200, {}),
    )
    assert code == cli.EXIT_NOTIFY_FAILED


def test_cli_zonder_mailconfig_met_treffer_is_failed(env, monkeypatch):  # noqa: F811
    for var in ("RESEND_API_KEY", "AH_MAIL_FROM", "AH_MAIL_TO"):
        monkeypatch.delenv(var, raising=False)
    code = cli.scan(
        SCHED.isoformat(),
        env / "s.enc",
        env / "d",
        good_post,
        lambda s, a: ok_payload(row(pct=90)),
        lambda: SCHED,
    )
    assert code == cli.EXIT_NOTIFY_FAILED


class _Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_resend_stuurt_eigen_user_agent_en_geen_standaard_urllib(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        seen["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr(notify.urllib.request, "urlopen", fake_urlopen)
    assert notify.resend_send("key")({"to": ["x"]}) is True
    assert seen["ua"] == notify.USER_AGENT and "urllib" not in seen["ua"]
    assert seen["auth"] == "Bearer key"


def _http_error(code, body):
    import io

    return notify.urllib.error.HTTPError("u", code, "m", {}, io.BytesIO(body))


def test_resend_fout_logt_status_en_naam_zonder_body(monkeypatch, capsys):
    body = b'{"name":"validation_error","message":"secret@example.com niet toegestaan"}'

    def boom(req, timeout):
        raise _http_error(403, body)

    monkeypatch.setattr(notify.urllib.request, "urlopen", boom)
    assert notify.resend_send("key")({}) is False
    out = capsys.readouterr().out
    assert "http=403" in out and "name=validation_error" in out
    assert "secret@example.com" not in out and "key" not in out.replace("http", "")


def test_resend_niet_json_body_en_netwerkfout(monkeypatch, capsys):
    monkeypatch.setattr(
        notify.urllib.request,
        "urlopen",
        lambda r, timeout: (_ for _ in ()).throw(
            _http_error(403, b"<html>error code: 1010</html>")
        ),
    )
    assert notify.resend_send("k")({}) is False
    assert "name=non_json" in capsys.readouterr().out

    def down(req, timeout):
        raise notify.urllib.error.URLError("dns")

    monkeypatch.setattr(notify.urllib.request, "urlopen", down)
    assert notify.resend_send("k")({}) is False
    assert "network=URLError" in capsys.readouterr().out


def test_cli_haalt_het_token_maar_een_keer_op_per_scan(env):  # noqa: F811
    posts = []

    def counting_post(path, body):
        posts.append(1)
        return good_post(path, body)

    code = cli.scan(
        SCHED.isoformat(),
        env / "s.enc",
        env / "d",
        counting_post,
        lambda s, a: ok_payload(row(pct=90)),
        lambda: SCHED,
        Mailer(),
        lambda q, v: (200, {"data": {"product": {"imagePack": []}}}),
    )
    assert code == 0 and len(posts) == 1
