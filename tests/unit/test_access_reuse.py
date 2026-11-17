import base64
import json
from datetime import timedelta
from pathlib import Path

from ah_scanner import auth, cli

from .test_client import ok_payload
from .test_filters_slots import row
from .test_storage_scan import SCHED, env  # noqa: F401

SECRET = "root-secret"


def jwt(exp):
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"h.{body}.s"


def test_expiry_uit_expires_in_jwt_of_onbekend():
    assert auth.expiry_of({"expires_in": 3600}, "x", now=1000) == 4600
    assert auth.expiry_of({}, jwt(5000), now=1000) == 5000
    assert auth.expiry_of({"expires_in": "kapot"}, jwt(7000), now=1000) == 7000
    assert auth.expiry_of({}, "geen-jwt", now=1000) is None
    assert auth.expiry_of({"expires_in": 0}, "", now=1000) is None


def test_seal_bewaart_access_token_en_unseal_geeft_nog_steeds_de_refresh_token(tmp_path: Path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("ref", SECRET, "acc", 9000.0))
    assert auth.unseal(path, SECRET) == "ref"
    assert auth.unseal_state(path, SECRET)["accessToken"] == "acc"
    assert auth.unseal_state(tmp_path / "nope", SECRET) == {}
    assert auth.unseal_state(path, "other") == {}


def test_seal_zonder_bekende_verlooptijd_bewaart_geen_access_token(tmp_path: Path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("ref", SECRET, "acc", None))
    assert "accessToken" not in auth.unseal_state(path, SECRET)


def test_cached_access_alleen_met_voldoende_marge(tmp_path: Path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("ref", SECRET, "acc", 2000.0))
    assert auth.cached_access(path, SECRET, now=1000) == "acc"
    assert auth.cached_access(path, SECRET, now=1750) == ""  # nog 250 s < marge van 300 s
    assert auth.cached_access(path, SECRET, now=3000) == ""  # verlopen
    assert auth.cached_access(tmp_path / "nope", SECRET, now=1000) == ""
    path.write_text(auth.seal("ref", SECRET))
    assert auth.cached_access(path, SECRET, now=1000) == ""  # geen verlooptijd bekend


def counting_post(payload):
    calls = []

    def post(path, body):
        calls.append(body["refreshToken"])
        return 200, dict(payload, refresh_token=f"rot{len(calls)}")

    post.calls = calls
    return post


def scan_args(root, post):
    return (
        (SCHED.isoformat(), root / "s.enc", root / "d"),
        dict(
            post=post,
            graphql=lambda s, a: ok_payload(row(pct=10)),
            now=lambda: SCHED,
            send=lambda payload: True,
            query=lambda q, v: (200, {}),
        ),
    )


def test_scan_hergebruikt_access_token_en_ververst_dan_niet(env, capsys):  # noqa: F811
    post = counting_post({"access_token": "acc", "expires_in": 7200})
    args, kw = scan_args(env, post)
    assert cli.scan(*args, **kw) == 0
    assert len(post.calls) == 1
    later = (
        (SCHED + timedelta(minutes=5)).isoformat(),
        args[1],
        args[2],
    )
    assert cli.scan(*later, **kw) == 0
    assert len(post.calls) == 1  # geen tweede verversing, dus geen tweede rotatie
    out = capsys.readouterr().out
    assert "AUTH_ACCESS reused=false expires_in_s=" in out and "AUTH_ACCESS reused=true" in out


def test_scan_ververst_elke_keer_als_verlooptijd_onbekend_is(env, capsys):  # noqa: F811
    post = counting_post({"access_token": "acc"})
    args, kw = scan_args(env, post)
    assert cli.scan(*args, **kw) == 0
    later = ((SCHED + timedelta(minutes=5)).isoformat(), args[1], args[2])
    assert cli.scan(*later, **kw) == 0
    assert len(post.calls) == 2  # onveranderd gedrag zonder bekende verlooptijd
    assert "expires_in_s=unknown" in capsys.readouterr().out
