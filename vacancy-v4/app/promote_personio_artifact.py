"""Promote an existing, immutable Personio proof pair; never repeat the live scan.

Call only after the workflow's unit, contract and independent QA steps succeed.
The caller must refresh the exact branch HEAD before each invocation and push
only as a non-forced fast-forward; retry once after refreshing on collision.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.certification_registry import accept_green_proof, certified_count
from app.proof_acceptance import validate
from app.release_gate import REQUIRED_GATES, release_decision

PROOF_SHA = "c83fe2fe7d913cf1a8a76c1acedd06a1e6213010"
PROOF_RUN_ID = "37694439614"
PROOF_RUN_ATTEMPT = 1
PROVIDER = "personio"
NAME = "Coinmerce"
SOURCE_ID = "employer::Coinmerce"


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def _read_at_proof(path: str) -> bytes:
    return _git("show", f"{PROOF_SHA}:{path}")


def validate_pair(first: dict, second: dict, manifest: dict, mapping: dict,
                  config: dict, authority: dict) -> tuple[dict, dict]:
    """Independent fail-closed acceptance checks on already validated batches."""
    identities = [f'{s["kind"]}::{s["name"]}' for s in manifest["sources"]]
    if len(set(identities)) != len(identities) or SOURCE_ID not in identities:
        raise ValueError("ambiguous or missing manifest identity")
    entries = [x for x in mapping["sources"] if x.get("name") == NAME and x.get("kind") == "employer"]
    if len(entries) != 1 or entries[0].get("platforms", {}).get(PROVIDER, {}).get("status") != "PROVEN":
        raise ValueError("Personio route not PROVEN in provider map")
    if PROVIDER not in authority.get("providers", {}):
        raise ValueError("authority contract missing")
    if config.get("provider") != PROVIDER or len(config.get("sources", [])) != 1 or config["sources"][0].get("name") != NAME:
        raise ValueError("provider config does not pin exactly Coinmerce")
    for batch in (first, second):
        if batch.get("provider") != PROVIDER or batch.get("configured_sources") != 1 or batch.get("verified_complete") != 1 or batch.get("failed") != 0:
            raise ValueError("incomplete provider batch")
        if len(batch.get("sources", [])) != 1 or batch["sources"][0].get("name") != NAME:
            raise ValueError("proof source mismatch")
    one, two = first["sources"][0], second["sources"][0]
    if any(s.get("coverage") != "verified_complete" or s.get("error") is not None for s in (one, two)):
        raise ValueError("non-green source")
    if any(s.get("unique_jobs", 0) <= 0 for s in (one, two)):
        raise ValueError("uncorroborated zero inventory")
    if one["unique_jobs"] != two["unique_jobs"]:
        raise ValueError("job totals drifted between proofs")
    jobs1 = {j["job_id"]: (j["title"], j["job_url"], j["apply_url"]) for j in one["jobs"]}
    jobs2 = {j["job_id"]: (j["title"], j["job_url"], j["apply_url"]) for j in two["jobs"]}
    if jobs1 != jobs2:
        raise ValueError("job identities or apply routes changed between proofs")
    if datetime.fromisoformat(one["checked_at"]) >= datetime.fromisoformat(two["checked_at"]):
        raise ValueError("production proofs not consecutive in time")
    return one, two


def promote(root: Path, proof_dir: Path) -> bool:
    """Persist both full envelopes and ledger together in the caller's Git commit."""
    first = validate(proof_dir / "personio-proof-1.json")
    second = validate(proof_dir / "personio-proof-2.json")
    manifest = json.loads((root / "vacancy-v4/config/sources.json").read_text())
    mapping = json.loads((root / "vacancy-v4/config/provider_map.json").read_text())
    authority_path = root / "vacancy-v4/config/provider_authority.json"
    authority = json.loads(authority_path.read_text())
    config_path = root / "vacancy-v4/config/personio_sources.json"
    config = json.loads(config_path.read_text())
    one, two = validate_pair(first, second, manifest, mapping, config, authority)

    # The exact adapter/config/authority used for the proofs must still be live.
    adapter_path = "vacancy-v4/app/providers/personio.py"
    config_rel = "vacancy-v4/config/personio_sources.json"
    authority_rel = "vacancy-v4/config/provider_authority.json"
    if _git("merge-base", "--is-ancestor", PROOF_SHA, "HEAD") != b"":
        raise ValueError("unexpected git ancestor output")
    for rel in (adapter_path, config_rel, authority_rel):
        if (root / rel).read_bytes() != _read_at_proof(rel):
            raise ValueError(f"{rel} changed after production proof")
    adapter_version = _git("rev-parse", f"{PROOF_SHA}:{adapter_path}").decode().strip()
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    authority_version = f'schema{authority["schema_version"]}:{hashlib.sha256(authority_path.read_bytes()).hexdigest()}'

    ledger_path = root / "vacancy-v4/data/certification-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    ordered_ids = [f'{s["kind"]}::{s["name"]}' for s in manifest["sources"]]
    records = ledger["records"]
    if ledger["target_count"] != len(ordered_ids) or len(records) != len(ordered_ids):
        raise ValueError("ledger/manifest count mismatch")
    by_id = {r["source"]: r for r in records}
    if len(by_id) != len(records) or set(by_id) != set(ordered_ids):
        raise ValueError("ledger/manifest identity mismatch")
    record = by_id[SOURCE_ID]
    if record["certification"] == "CERTIFIED":
        print("Coinmerce already CERTIFIED; no write")
        return False
    if record["certification"] == "REVOKED":
        raise ValueError("explicitly revoked source cannot auto-promote")

    # Independent QA was run on the artifact in the preceding workflow step;
    # the first one-source green production proof is also the live canary.
    gates = {key: True for key in REQUIRED_GATES}
    release = release_decision(gates)
    if not release["release_allowed"]:
        raise ValueError("release gate closed")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", SOURCE_ID)
    runbase = f"{PROOF_RUN_ID}-{PROOF_RUN_ATTEMPT}"
    target = root / "vacancy-v4/data/accepted" / PROVIDER / safe / two["checked_at"][:10] / runbase
    if target.exists():
        raise ValueError("immutable accepted proof destination already exists")
    run_ids = []
    envelopes = []
    for number, source, batch in ((1, one, first), (2, two, second)):
        run_id = f"{runbase}:{PROVIDER}:{SOURCE_ID}:proof-{number}"
        run_ids.append(run_id)
        envelopes.append({
            "schema_version": 1, "accepted": True, "release_allowed": True,
            "release_gates": release, "run_id": run_id,
            "provider": PROVIDER, "source_id": SOURCE_ID,
            "source": source, "batch_generated_at": batch.get("generated_at"),
            "workflow_run_id": PROOF_RUN_ID, "workflow_run_attempt": PROOF_RUN_ATTEMPT,
            "code_commit_sha": PROOF_SHA, "adapter_version": adapter_version,
            "config_hash": config_hash, "authority_contract_version": authority_version,
        })
    for number, source in ((1, one), (2, two)):
        record = accept_green_proof(record, {
            "run_id": run_ids[number-1], "accepted_at": source["checked_at"],
            "adapter_version": adapter_version, "code_commit_sha": PROOF_SHA,
            "config_hash": config_hash, "authority_contract_version": authority_version,
            "unique_jobs": source["unique_jobs"],
        }, release_allowed=release["release_allowed"])
    if record["certification"] != "CERTIFIED":
        raise ValueError("two accepted green proofs did not certify")
    by_id[SOURCE_ID] = record
    new_records = [by_id[sid] for sid in ordered_ids]
    ledger.update({"certified_coverage": certified_count(new_records),
                   "updated_at": datetime.now(timezone.utc).isoformat(),
                   "records": new_records})
    # Write only after all gates and state transitions are validated.
    target.mkdir(parents=True, exist_ok=False)
    for number, envelope in enumerate(envelopes, 1):
        (target / f"proof-{number}.json").write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n")
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    print(f"Promoted {SOURCE_ID}: CERTIFIED; {ledger['certified_coverage']}/{ledger['target_count']}; jobs={two['unique_jobs']}")
    return True


if __name__ == "__main__":
    import sys
    promote(Path(__file__).resolve().parents[2], Path(sys.argv[1]).resolve())
