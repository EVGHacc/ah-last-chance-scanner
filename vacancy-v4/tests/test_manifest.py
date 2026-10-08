import json
from pathlib import Path
import sys, unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.registry import load_sources

class ManifestTests(unittest.TestCase):
    def test_manifest_count_matches_live_target(self):
        data = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
        sources = load_sources()
        self.assertEqual(len(sources), data["target_count"])
        self.assertEqual(len({(s.kind, s.name) for s in sources}), data["target_count"])

    def test_all_persistent_registries_match_manifest(self):
        manifest = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
        mapping = json.loads((ROOT / "config" / "provider_map.json").read_text(encoding="utf-8"))
        ledger = json.loads((ROOT / "data" / "certification-ledger.json").read_text(encoding="utf-8"))
        identities = lambda rows: [(row["kind"], row["name"]) for row in rows]
        expected = set(identities(manifest["sources"]))
        self.assertEqual(len(expected), manifest["target_count"])
        for rows in (mapping["sources"], ledger["records"]):
            actual = identities(rows)
            self.assertEqual(len(actual), len(set(actual)))
            self.assertEqual(set(actual), expected)
        self.assertEqual(mapping["source_manifest_count"], manifest["target_count"])
        self.assertEqual(ledger["target_count"], manifest["target_count"])
        self.assertEqual(ledger["certified_coverage"],
                         sum(r["certification"] == "CERTIFIED" for r in ledger["records"]))

    def test_v2_exclusions_are_not_targets(self):
        names = {s.name for s in load_sources()}
        self.assertNotIn("DB Contractors UK", names)
        self.assertNotIn("Risk Talent Associates", names)

    def test_manifest_contains_identity_only(self):
        data = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
        allowed = {"kind", "name", "official_domain", "seed_urls", "allowed_domains"}
        forbidden = {"coverage", "status", "evidence", "no_public_hint", "verified", "target_proven"}
        for row in data["sources"]:
            self.assertEqual(set(row), allowed)
            self.assertTrue(forbidden.isdisjoint(row))

    def test_priority_and_new_source_presence(self):
        by_name = {s.name: s for s in load_sources()}
        self.assertIn("ING", by_name)
        self.assertIn("Rabobank", by_name)
        self.assertIn("AuditCarriere", by_name)
        self.assertEqual(by_name["AuditCarriere"].kind, "job_board")
        self.assertEqual(by_name["AuditCarriere"].official_domain, "auditcarriere.nl")

        expected_vbin_employers = {
            "Worldpay": "worldpay.com",
            "CM.com": "cm.com",
            "Uber": "uber.com",
            "CCV": "ccv.eu",
            "Buckaroo": "buckaroo.nl",
            "Online Payment Platform": "onlinepaymentplatform.com",
            "Intersolve": "intersolve.com",
        }
        for name, domain in expected_vbin_employers.items():
            self.assertIn(name, by_name)
            self.assertEqual(by_name[name].kind, "employer")
            self.assertEqual(by_name[name].official_domain, domain)

if __name__ == "__main__":
    unittest.main()
