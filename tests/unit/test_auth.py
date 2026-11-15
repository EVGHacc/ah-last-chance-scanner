from pathlib import Path

import pytest

from ah_scanner import auth, cli

SECRET = "root-secret"


def make_post(responses):
    """Geeft per aanroep het volgende (status, payload) terug en logt de gebruikte tokens."""
    calls = []

    def post(path, body):
        calls.append(body["refreshToken"])
        return responses.pop(0)

    post.calls = calls
    return post


def ok(access="acc", refresh="new"):
    return 200, {"access_token": access, "refresh_token": refresh}


def test_seal_roundtrip(tmp_path: Path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("tok", SECRET))
    assert auth.unseal(path, SECRET) == "tok"


def test_unseal_wrong_secret_or_missing(tmp_path: Path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("tok", SECRET))
    assert auth.unseal(path, "other") == ""
    assert auth.unseal(tmp_path / "nope", SECRET) == ""


def test_refresh_uses_sealed_token_first(tmp_path: Path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("sealed-token", SECRET))
    post = make_post([ok(refresh="rotated")])
    session = auth.refresh_session(SECRET, path, post=post)
    assert post.calls == ["sealed-token"]
    assert session.rotated and session.refresh_token == "rotated"


def test_falls_back_to_secret_when_sealed_rejected(tmp_path: Path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("stale", SECRET))
    post = make_post([(401, {}), ok()])
    session = auth.refresh_session(SECRET, path, post=post)
    assert post.calls == ["stale", SECRET]
    assert session.access_token == "acc"


def test_reauth_required_when_all_rejected(tmp_path: Path):
    post = make_post([(401, {})])
    with pytest.raises(auth.AuthError) as exc:
        auth.refresh_session(SECRET, None, post=post)
    assert exc.value.code == "AUTH_REAUTH_REQUIRED"


def test_transient_errors_are_bounded():
    post = make_post([(503, {}), (503, {}), (503, {})])
    with pytest.raises(auth.AuthError) as exc:
        auth.refresh_session(SECRET, None, post=post, sleep=lambda _s: None)
    assert exc.value.code == "AUTH_REFRESH_RETRY_EXHAUSTED"
    assert len(post.calls) == 3


def test_transient_then_success():
    post = make_post([(503, {}), ok()])
    session = auth.refresh_session(SECRET, None, post=post, sleep=lambda _s: None)
    assert session.access_token == "acc"


def test_missing_secret():
    with pytest.raises(auth.AuthError) as exc:
        auth.refresh_session("  ", None, post=make_post([]))
    assert exc.value.code == "AUTH_REAUTH_REQUIRED"


def test_non_retryable_status():
    with pytest.raises(auth.AuthError) as exc:
        auth.refresh_session(SECRET, None, post=make_post([(418, {})]))
    assert exc.value.code == "AUTH_REFRESH_FAILED"


def test_persist_rotation_only_when_rotated(tmp_path: Path):
    path = tmp_path / "d" / "s.enc"
    same = auth.Session("a", "t", rotated=False)
    assert auth.persist_rotation(same, SECRET, path) is False
    assert not path.exists()
    assert auth.persist_rotation(auth.Session("a", "t2", True), SECRET, path) is True
    assert auth.unseal(path, SECRET) == "t2"


def test_cli_auth_check_ok_never_prints_tokens(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AH_REFRESH_TOKEN", SECRET)
    state = tmp_path / "s.enc"
    code = cli.auth_check(state, True, post=make_post([ok(access="ACCESS", refresh="ROT")]))
    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert "persisted=True" in out
    assert "ACCESS" not in out and "ROT" not in out and SECRET not in out
    assert auth.unseal(state, SECRET) == "ROT"


def test_cli_auth_check_reauth_exit_code(tmp_path, monkeypatch):
    monkeypatch.setenv("AH_REFRESH_TOKEN", SECRET)
    assert cli.auth_check(tmp_path / "s", False, post=make_post([(401, {})])) == cli.EXIT_REAUTH
