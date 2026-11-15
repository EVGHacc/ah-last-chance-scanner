from pathlib import Path

from ah_scanner import policy

ROOT = Path(__file__).resolve().parents[2]


def test_workflow_zonder_test_faalt():
    assert policy.evaluate_changes([".github/workflows/scan.yml"])


def test_workflow_met_test_slaagt():
    paths = [".github/workflows/scan.yml", "tests/test_workflow_v2_scan.py"]
    assert policy.evaluate_changes(paths) == []


def test_code_zonder_test_faalt_en_met_test_slaagt():
    assert policy.evaluate_changes(["src/ah_scanner/client.py"])
    assert policy.evaluate_changes(["src/ah_scanner/client.py", "tests/unit/test_client.py"]) == []
    assert policy.evaluate_changes(["worker/src/index.js", "worker/test/index.test.js"]) == []


def test_docs_vereisen_niets():
    assert policy.evaluate_changes(["README.md"]) == []


def test_static_review_van_deze_repo_slaagt():
    assert policy.static_review(ROOT) == []


def test_static_review_vindt_schedule_en_vreemde_workflow(tmp_path):
    wf = tmp_path / ".github/workflows"
    wf.mkdir(parents=True)
    for name in policy.ALLOWED_WORKFLOWS:
        jobs = "contents: read\nchanges:\npolicy:\nah-tests:\nindependent-review:\n"
        (wf / name).write_text(jobs)
    (wf / "scan.yml").write_text("on:\n  schedule:\n")
    (wf / "oud.yml").write_text("x")
    issues = policy.static_review(tmp_path)
    assert any("scan.yml" in i and "schedule" in i for i in issues)
    assert any("oud.yml" in i for i in issues)


def test_lege_base_geeft_geen_wijzigingen():
    assert policy.changed_files("", "HEAD") == []
    assert policy.changed_files("0000000", "HEAD") == []


def test_main_static_review_en_diff(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert policy.main(["--static-review"]) == 0
    assert "POLICY PASS" in capsys.readouterr().out
    assert policy.main(["--base", ""]) == 0
    monkeypatch.setattr(policy, "changed_files", lambda b, h: [".github/workflows/scan.yml"])
    assert policy.main(["--base", "abc"]) == 1
    assert "POLICY FAIL" in capsys.readouterr().out
