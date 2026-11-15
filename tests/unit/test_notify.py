from datetime import date

from ah_scanner import cli, notify
from ah_scanner.models import INCOMPLETE, OK, Item, ScanResult, StoreResult

from .test_client import ok_payload
from .test_filters_slots import row
from .test_storage_scan import SCHED, env, good_post  # noqa: F401

DAY = date(2026, 11, 15)


def item(pid=1, pct=80.0):
    return Item(pid, "Rundergehakt", "AH", "500 g", "Vlees", pct, 2, "5.00", "1.00", "2026-11-15")


def scan(items, status=OK, store_id=1463):
    store = StoreResult(store_id, "AH Test", True, len(items), tuple(items), tuple(items))
    return ScanResult(
        SCHED.isoformat(), SCHED.isoformat(), SCHED.isoformat(), 0, False, status, (store,)
    )


class Mailer:
    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def __call__(self, payload):
        self.sent.append(payload)
        return self.ok


def test_geen_mail_zonder_nieuwe_items(tmp_path):
    m = Mailer()
    assert notify.notify(scan([]), DAY, tmp_path, m, "a@x", "b@x") == "none" and not m.sent


def test_dedup_geen_tweede_mail(tmp_path):
    m = Mailer()
    assert notify.notify(scan([item()]), DAY, tmp_path, m, "a@x", "b@x") == "sent"
    assert notify.notify(scan([item()]), DAY, tmp_path, m, "a@x", "b@x") == "none"
    assert len(m.sent) == 1


def test_nieuw_item_wordt_wel_gemeld(tmp_path):
    m = Mailer()
    notify.notify(scan([item(1)]), DAY, tmp_path, m, "a@x", "b@x")
    notify.notify(scan([item(1), item(2)]), DAY, tmp_path, m, "a@x", "b@x")
    assert (
        len(m.sent) == 2
        and "x" in m.sent[1]["subject"]
        and m.sent[1]["subject"].startswith("AH Laatste Kans: 1x")
    )


def test_mislukte_verzending_bewaart_niets_en_probeert_opnieuw(tmp_path):
    assert notify.notify(scan([item()]), DAY, tmp_path, Mailer(False), "a@x", "b@x") == "failed"
    assert notify.notify(scan([item()]), DAY, tmp_path, Mailer(True), "a@x", "b@x") == "sent"


def test_zelfde_product_andere_winkel_is_apart(tmp_path):
    m = Mailer()
    notify.notify(scan([item()], store_id=1463), DAY, tmp_path, m, "a@x", "b@x")
    assert notify.notify(scan([item()], store_id=1348), DAY, tmp_path, m, "a@x", "b@x") == "sent"


def test_state_wordt_na_7_dagen_opgeschoond(tmp_path):
    state = {"2026-11-01": ["k"], "2026-11-14": ["k"]}
    notify.save_state(tmp_path, state, DAY)
    assert list(notify.load_state(tmp_path)) == ["2026-11-14"]


def test_incomplete_scan_vermeldt_status_in_mail(tmp_path):
    m = Mailer()
    notify.notify(scan([item()], status=INCOMPLETE), DAY, tmp_path, m, "a@x", "b@x")
    assert "INCOMPLETE" in m.sent[0]["text"]


def test_cli_scan_mailt_en_dedupliceert(env):  # noqa: F811
    m = Mailer()
    kw = dict(
        post=good_post, graphql=lambda s, a: ok_payload(row(pct=90)), now=lambda: SCHED, send=m
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
