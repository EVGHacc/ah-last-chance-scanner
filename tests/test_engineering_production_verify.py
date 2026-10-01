import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


verify = load_module("production_verify", "scripts/production_verify.py")


class VacancyProductionVerifierTests(unittest.TestCase):
    def write_fixture(self, tmp, *, strong=True, observed=2, total=2):
        root = Path(tmp)
        registry = root / "registry.tsv"
        registry.write_text(
            "kind\tname\n"
            "employer\tAlpha\n"
            "recruiter\tBeta\n",
            encoding="utf-8",
        )
        evidence = []
        if strong:
            evidence = [
                {
                    "url": "https://example.com/jobs",
                    "api_complete": True,
                    "api_terminal": True,
                    "official_total": total,
                    "job_link_count": observed,
                }
            ]
        snapshot = root / "latest.json"
        payload = {
            "total_expected": 2,
            "total_classified": 2,
            "complete": True,
            "qa": {"passed": True},
            "vacancy_coverage_counts": {
                "verified_complete": 1,
                "partial": 1,
            },
            "technical_failures": [
                {"name": "Beta", "kind": "recruiter", "error": "blocked"}
            ],
            "live_relevant_jobs": [
                {
                    "organisation": "Alpha",
                    "title": "Head of Risk",
                    "url": "https://example.com/jobs/1",
                    "apply_live": True,
                    "live": True,
                    "board_present": True,
                    "http_status": 200,
                }
            ],
            "organisations": [
                {
                    "kind": "employer",
                    "name": "Alpha",
                    "status": "official_ats_scanned",
                    "vacancy_coverage": "verified_complete",
                    "listing_evidence": evidence,
                    "inventory_audit": {
                        "official_total": total,
                        "observed_job_links": observed,
                        "failure": None,
                        "checked_at": "2026-10-01T10:00:00+00:00",
                    },
                },
                {
                    "kind": "recruiter",
                    "name": "Beta",
                    "status": "technical_failure",
                    "vacancy_coverage": "partial",
                    "listing_evidence": [],
                    "inventory_audit": {
                        "official_total": None,
                        "observed_job_links": 1,
                        "failure": "blocked",
                        "checked_at": "2026-10-01T10:00:00+00:00",
                    },
                },
            ],
        }
        snapshot.write_text(json.dumps(payload), encoding="utf-8")
        return snapshot, registry

    def test_accepts_recomputed_exhaustive_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot, registry = self.write_fixture(tmp)
            report = verify.verify_vacancy(snapshot, registry)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["proven_sources"], 1)

    def test_rejects_verified_complete_without_exhaustive_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot, registry = self.write_fixture(tmp, strong=False)
            with self.assertRaises(AssertionError):
                verify.verify_vacancy(snapshot, registry)

    def test_rejects_official_total_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot, registry = self.write_fixture(tmp, observed=1, total=2)
            with self.assertRaises(AssertionError):
                verify.verify_vacancy(snapshot, registry)

    def test_rejects_registry_snapshot_identity_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot, registry = self.write_fixture(tmp)
            payload = json.loads(snapshot.read_text(encoding="utf-8"))
            payload["organisations"][0]["name"] = "Wrong"
            snapshot.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AssertionError):
                verify.verify_vacancy(snapshot, registry)


if __name__ == "__main__":
    unittest.main()
