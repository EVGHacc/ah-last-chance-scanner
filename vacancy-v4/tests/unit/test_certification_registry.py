import pytest

from app.certification_registry import (
    accept_green_proof, apply_health, new_record, revoke
)


def proof(run_id, jobs=3):
    return {
        "run_id": run_id,
        "accepted_at": "2026-10-02T20:00:00+00:00",
        "adapter_version": "1",
        "code_commit_sha": "abc123",
        "config_hash": "cfg",
        "authority_contract_version": "1",
        "unique_jobs": jobs,
    }


def test_two_green_proofs_required_for_certification():
    first = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
    assert first["certification"] == "VERIFYING"
    second = accept_green_proof(first, proof("r2"), release_allowed=True)
    assert second["certification"] == "CERTIFIED"
    assert second["certification_provenance"] == ["r1", "r2"]


def test_transient_health_degradation_does_not_revoke_certification():
    r = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
    r = accept_green_proof(r, proof("r2"), release_allowed=True)
    degraded = apply_health(r, "DEGRADED")
    assert degraded["certification"] == "CERTIFIED"
    assert degraded["health"] == "DEGRADED"


def test_closed_release_gate_cannot_accept_proof():
    with pytest.raises(ValueError, match="release gate closed"):
        accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=False)


def test_revocation_requires_quorum():
    r = new_record("ashby", "openai")
    with pytest.raises(ValueError, match="quorum"):
        revoke(r, reason="temporary drift")
    revoked = revoke(r, reason="schema contract broken", structural_evidence=True)
    assert revoked["certification"] == "REVOKED"
