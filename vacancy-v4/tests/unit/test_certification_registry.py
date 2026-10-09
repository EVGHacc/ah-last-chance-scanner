import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.certification_registry import (
    accept_green_proof,
    apply_health,
    new_record,
    record_failed_recertification,
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

    def test_changed_provenance_cannot_complete_two_proofs(self):
        first = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
        changed = proof("r2")
        changed["config_hash"] = "different"
        with self.assertRaisesRegex(ValueError, "provenance changed"):
            accept_green_proof(first, changed, release_allowed=True)

    def test_failed_proof_breaks_chain_and_allows_new_version(self):
        first = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
        reset = record_failed_recertification(first)
        changed = proof("r2")
        changed["config_hash"] = "new-config"
        second = accept_green_proof(reset, changed, release_allowed=True)
        self.assertEqual(second["certification"], "VERIFYING")
        third = proof("r3")
        third["config_hash"] = "new-config"
        certified = accept_green_proof(second, third, release_allowed=True)
        self.assertEqual(certified["certification"], "CERTIFIED")
        self.assertEqual(certified["certification_provenance"], ["r2", "r3"])

    def test_reproof_preserves_certification_provenance(self):
        first = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
        certified = accept_green_proof(first, proof("r2"), release_allowed=True)
        refreshed = accept_green_proof(certified, proof("r3"), release_allowed=True)
        self.assertEqual(refreshed["certification"], "CERTIFIED")
        self.assertEqual(refreshed["certification_provenance"], ["r1", "r2"])

    def test_transient_health_degradation_does_not_revoke_certification(self):
        record = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
        record = accept_green_proof(record, proof("r2"), release_allowed=True)
        degraded = apply_health(record, "DEGRADED")
        self.assertEqual(degraded["certification"], "CERTIFIED")
        self.assertEqual(degraded["health"], "DEGRADED")

    def test_zero_or_invalid_inventory_rejected_at_state_machine_boundary(self):
        for jobs in (0, -1, True, False, "1", 1.0):
            with self.subTest(jobs=jobs):
                record = new_record("ashby", "openai")
                with self.assertRaisesRegex(ValueError, "positive integer unique_jobs"):
                    accept_green_proof(record, proof("r1", jobs=jobs), release_allowed=True)
                self.assertEqual(record["certification"], "UNPROVEN")
                self.assertEqual(record["accepted_proofs"], [])

    def test_invalid_reproof_cannot_refresh_existing_certification(self):
        first = accept_green_proof(new_record("ashby", "openai"), proof("r1"), release_allowed=True)
        certified = accept_green_proof(first, proof("r2"), release_allowed=True)
        with self.assertRaisesRegex(ValueError, "positive integer unique_jobs"):
            accept_green_proof(certified, proof("r3", jobs=0), release_allowed=True)
        self.assertEqual(certified["certified_job_count"], 3)
        self.assertEqual(certified["accepted_proofs"], ["r1", "r2"])

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
