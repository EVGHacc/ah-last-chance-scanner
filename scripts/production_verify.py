#!/usr/bin/env python3
"""Read-only production evidence verifier for both scanners."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path


def _load_json(path: Path) -> dict:
    if not path.is_file():
        raise AssertionError(f"missing production artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _registry_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise AssertionError("vacancy registry is empty")
    identities = [(row.get("kind"), row.get("name")) for row in rows]
    if len(identities) != len(set(identities)):
        raise AssertionError("vacancy registry contains duplicate kind/name identities")
    return rows


def _has_complete_inventory_evidence(org: dict) -> bool:
    for evidence in org.get("listing_evidence") or []:
        if evidence.get("static_complete_evidence") is True:
            return True
        if evidence.get("static_board_complete") is True:
            return True
        if evidence.get("embedded_complete") is True:
            return True
        if evidence.get("api_complete") is True and evidence.get("api_terminal") is True:
            return True
        total = evidence.get("official_total")
        observed = evidence.get("browser_inventory_count")
        if (
            evidence.get("browser_terminal") is True
            and type(total) is int
            and type(observed) is int
            and observed == total
        ):
            return True
    return False


def verify_vacancy(
    snapshot_path: Path = Path("vacancy-monitor/data/latest.json"),
    registry_path: Path = Path("vacancy-monitor/registry.tsv"),
) -> dict:
    """Recompute the critical production claims from persisted evidence."""
    rows = _registry_rows(registry_path)
    expected = len(rows)
    snapshot = _load_json(snapshot_path)
    organisations = snapshot.get("organisations") or []

    assert snapshot.get("total_expected") == expected, (
        snapshot.get("total_expected"),
        expected,
    )
    assert snapshot.get("total_classified") == expected
    assert snapshot.get("complete") is True
    assert len(organisations) == expected

    registry_ids = {(row["kind"], row["name"]) for row in rows}
    snapshot_ids = {(org.get("kind"), org.get("name")) for org in organisations}
    assert snapshot_ids == registry_ids, "snapshot/registry identity mismatch"

    assert snapshot.get("qa", {}).get("passed") is True
    assert all(
        isinstance(org.get("inventory_audit"), dict)
        and org["inventory_audit"].get("checked_at")
        for org in organisations
    ), "missing inventory audit/timestamp"

    coverage = Counter(org.get("vacancy_coverage") for org in organisations)
    published_coverage = snapshot.get("vacancy_coverage_counts") or {}
    for state, count in coverage.items():
        assert published_coverage.get(state, 0) == count, (
            "coverage count mismatch",
            state,
            published_coverage.get(state),
            count,
        )

    technical = {org["name"] for org in organisations if org.get("status") == "technical_failure"}
    published_technical = {item.get("name") for item in snapshot.get("technical_failures") or []}
    assert technical == published_technical, "technical-failure list mismatch"

    for org in organisations:
        audit = org["inventory_audit"]
        state = org.get("vacancy_coverage")
        if state == "verified_complete":
            assert audit.get("failure") is None, f"{org['name']}: complete with audit failure"
            assert _has_complete_inventory_evidence(org), (
                f"{org['name']}: verified_complete without exhaustive evidence"
            )
            total = audit.get("official_total")
            observed = audit.get("observed_job_links")
            if type(total) is int:
                assert observed == total, (
                    f"{org['name']}: official total {total} != observed {observed}"
                )

    bad_live = []
    for job in snapshot.get("live_relevant_jobs") or []:
        if not (
            job.get("apply_live") is True
            and job.get("live") is True
            and job.get("board_present") is True
            and job.get("http_status") == 200
        ):
            bad_live.append((job.get("organisation"), job.get("title"), job.get("url")))
    assert not bad_live, f"invalid published live jobs: {bad_live[:5]}"

    proven = coverage.get("verified_complete", 0) + coverage.get(
        "verified_no_public_board", 0
    )
    report = {
        "project": "vacancy",
        "registry_entries": expected,
        "proven_sources": proven,
        "technical_failures": len(technical),
        "live_jobs_checked": len(snapshot.get("live_relevant_jobs") or []),
        "result": "PASS",
    }
    print(json.dumps(report, ensure_ascii=False))
    return report


def verify_ah(root: Path = Path(".")) -> dict:
    """Delegate AH production proof to the pre-existing independent read-only verifier."""
    module_path = root / "scripts" / "independent_qa.py"
    spec = importlib.util.spec_from_file_location("ah_independent_qa", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.verify(root / "data", require_complete=True)
    return {"project": "ah", "result": "PASS", **report}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=("ah", "vacancy"), required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--registry", type=Path)
    args = parser.parse_args()

    if args.project == "ah":
        verify_ah()
    else:
        verify_vacancy(
            args.snapshot or Path("vacancy-monitor/data/latest.json"),
            args.registry or Path("vacancy-monitor/registry.tsv"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
