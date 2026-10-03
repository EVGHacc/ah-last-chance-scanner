import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.certification_registry import (
    accept_green_proof,
    apply_health,
    new_record,
    revoke,
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


class CertificationRegistryTests(unittest.TestCase):
    def test_two_green_proofs_required_for_certification(self):
        first = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
        self.assertEqual(first["certification"], "VERIFYING")
        second = accept_green_proof(first, proof("r2"), release_allowed=True)
        self.assertEqual(second["certification"], "CERTIFIED")
        self.assertEqual(second["certification_provenance"], ["r1", "r2"])

    def test_transient_health_degradation_does_not_revoke_certification(self):
        record = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
        record = accept_green_proof(record, proof("r2"), release_allowed=True)
        degraded = apply_health(record, "DEGRADED")
        self.assertEqual(degraded["certification"], "CERTIFIED")
        self.assertEqual(degraded["health"], "DEGRADED")

    def test_closed_release_gate_cannot_accept_proof(self):
        with self.assertRaisesRegex(ValueError, "release gate closed"):
            accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=False)

    def test_revocation_requires_quorum(self):
        record = new_record("ashby", "openai")
        with self.assertRaisesRegex(ValueError, "quorum"):
            revoke(record, reason="temporary drift")
        revoked = revoke(record, reason="schema contract broken", structural_evidence=True)
        self.assertEqual(revoked["certification"], "REVOKED")


if __name__ == "__main__":
    unittest.main()
