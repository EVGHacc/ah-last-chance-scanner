"""report en export moeten werken zonder werkende cryptography (bijv. een kapotte systeemlib)."""

import importlib
import sys

import pytest

from ah_scanner import auth, cli


@pytest.fixture
def kapotte_cryptography(monkeypatch):
    """Elke import van cryptography faalt, ook al ge-importeerde submodules."""
    for name in [n for n in sys.modules if n == "cryptography" or n.startswith("cryptography.")]:
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "cryptography", None)
    yield
    # modules die tijdens de test opnieuw zijn geladen terugzetten
    importlib.reload(auth)
    importlib.reload(cli)


def test_cli_en_report_laden_zonder_cryptography(kapotte_cryptography, tmp_path, capsys):
    importlib.reload(auth)  # herlaad zonder werkende cryptography: mag niet crashen
    importlib.reload(cli)
    out = tmp_path / "out"
    assert cli.main(["report", "--data-root", str(tmp_path / "leeg"), "--out", str(out)]) == 0
    assert "REPORT week=leeg" in capsys.readouterr().out


def test_export_werkt_zonder_cryptography(kapotte_cryptography, tmp_path, capsys):
    importlib.reload(auth)
    importlib.reload(cli)
    code = cli.main(["export", "--data-root", str(tmp_path), "--out", str(tmp_path / "o")])
    assert code == 0 and "EXPORT days=0" in capsys.readouterr().out


def test_seal_geeft_duidelijke_importerror_bij_kapotte_installatie(kapotte_cryptography):
    importlib.reload(auth)
    with pytest.raises(ImportError):
        auth.seal("token", "geheim")


def test_unseal_meldt_kapotte_installatie_luid_maar_ontbrekend_bestand_stil(
    kapotte_cryptography, tmp_path
):
    importlib.reload(auth)
    assert auth.unseal(tmp_path / "bestaat-niet", "geheim") == ""  # geen cryptography nodig
    kapot = tmp_path / "state.enc"
    kapot.write_text('{"version":1,"nonce":"AAAA","ciphertext":"AAAA"}', encoding="utf-8")
    with pytest.raises(ImportError):
        auth.unseal(kapot, "geheim")


def test_normale_werking_blijft_gelijk(tmp_path):
    path = tmp_path / "s.enc"
    path.write_text(auth.seal("tok", "geheim"), encoding="utf-8")
    assert auth.unseal(path, "geheim") == "tok"
    assert auth.unseal(path, "ander") == ""


def test_scan_en_auth_check_falen_vroeg_zonder_token_te_verversen(kapotte_cryptography, tmp_path):
    importlib.reload(auth)
    importlib.reload(cli)
    calls = []

    def post(path, body):
        calls.append(path)
        return 200, {"access_token": "a", "refresh_token": "nieuw"}

    state = tmp_path / "s.enc"
    code = cli.scan("2026-11-16T17:30:00+01:00", state, tmp_path / "d", post)
    assert code == cli.EXIT_SCAN_INVALID and calls == []  # niet ververst, dus niets gerouteerd
    assert cli.auth_check(state, True, post) == cli.EXIT_TRANSIENT and calls == []
    assert not (tmp_path / "d").exists()
