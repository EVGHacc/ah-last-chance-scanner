"""Authoritative v4 certification state machine.

Scanner/provider code may emit observations, but only this acceptance module may
change durable certification state. Runtime health/freshness never implicitly
revokes certification.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

CERT_STATES = {"UNPROVEN", "VERIFYING", "CERTIFIED", "REVOKED"}
HEALTH_STATES = {"HEALTHY", "DEGRADED", "STALE"}


def new_record(provider: str, source: str) -> dict:
    return {
        "provider": provider,
        "source": source,
        "certification": "UNPROVEN",
        "health": "STALE",
        "accepted_proofs": [],
        "consecutive_green_proofs": 0,
        "certification_provenance": None,
        "adapter_version": None,
        "code_commit_sha": None,
        "config_hash": None,
        "authority_contract_version": None,
        "certified_job_count": None,
        "freshness_at": None,
        "revocation_reason": None,
        "revoked_at": None,
    }


def apply_health(record: dict, health: str, freshness_at: str | None = None) -> dict:
    if health not in HEALTH_STATES:
        raise ValueError("invalid health")
    out = deepcopy(record)
    out["health"] = health
    if freshness_at is not None:
        out["freshness_at"] = freshness_at
    return out


def accept_green_proof(record: dict, proof: dict, *, release_allowed: bool) -> dict:
    """Accept one immutable green proof after the central release gate."""
    if not release_allowed:
        raise ValueError("release gate closed")
    required = (
        "run_id", "accepted_at", "adapter_version", "code_commit_sha",
        "config_hash", "authority_contract_version", "unique_jobs",
    )
    if any(proof.get(key) in (None, "") for key in required):
        raise ValueError("proof provenance incomplete")
    if proof["run_id"] in record.get("accepted_proofs", []):
        raise ValueError("proof run_id already accepted")

    # A proof for an already certified source refreshes health, not certification.
    was_certified = record.get("certification") == "CERTIFIED"
    if record.get("accepted_proofs") and not was_certified:
        previous = (record.get("adapter_version"), record.get("code_commit_sha"),
                    record.get("config_hash"), record.get("authority_contract_version"))
        current = tuple(proof[key] for key in ("adapter_version", "code_commit_sha",
                                                "config_hash", "authority_contract_version"))
        if previous != current:
            raise ValueError("proof provenance changed between consecutive green proofs")

    out = deepcopy(record)
    out["accepted_proofs"] = [*out.get("accepted_proofs", []), proof["run_id"]]
    out["consecutive_green_proofs"] = out.get("consecutive_green_proofs", 0) + 1
    out["adapter_version"] = proof["adapter_version"]
    out["code_commit_sha"] = proof["code_commit_sha"]
    out["config_hash"] = proof["config_hash"]
    out["authority_contract_version"] = proof["authority_contract_version"]
    out["freshness_at"] = proof["accepted_at"]
    out["health"] = "HEALTHY"
    if was_certified or out["consecutive_green_proofs"] >= 2:
        out["certification"] = "CERTIFIED"
        out["certified_job_count"] = proof["unique_jobs"]
        if not was_certified:
            out["certification_provenance"] = out["accepted_proofs"][-2:]
        out["revocation_reason"] = None
        out["revoked_at"] = None
    else:
        out["certification"] = "VERIFYING"
    return out


def record_failed_recertification(record: dict) -> dict:
    out = deepcopy(record)
    out["consecutive_green_proofs"] = 0
    return out


def revoke(record: dict, *, reason: str, structural_evidence: bool = False,
           repeated_same_failure: bool = False, revoked_at: str | None = None) -> dict:
    """Explicit revocation only after structural evidence or failure quorum."""
    if not reason.strip():
        raise ValueError("revocation reason required")
    if not (structural_evidence or repeated_same_failure):
        raise ValueError("revocation quorum not met")
    out = deepcopy(record)
    out["certification"] = "REVOKED"
    out["consecutive_green_proofs"] = 0
    out["revocation_reason"] = reason
    out["revoked_at"] = revoked_at or datetime.now(timezone.utc).isoformat()
    return out


def certified_count(records: list[dict]) -> int:
    return sum(record.get("certification") == "CERTIFIED" for record in records)
