import json
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.registry import load_sources
class ManifestTests(unittest.TestCase):
 def test_exactly_105_clean_sources(self):
  sources=load_sources();self.assertEqual(len(sources),105);self.assertEqual(len({(s.kind,s.name) for s in sources}),105)
 def test_v2_exclusions_are_not_targets(self):
  names={s.name for s in load_sources()};self.assertNotIn("DB Contractors UK",names);self.assertNotIn("Risk Talent Associates",names)
 def test_manifest_contains_identity_only(self):
  data=json.loads((ROOT/"config"/"sources.json").read_text(encoding="utf-8"));allowed={"kind","name","official_domain","seed_urls","allowed_domains"};forbidden={"coverage","status","evidence","no_public_hint","verified","target_proven"}
  for row in data["sources"]:self.assertEqual(set(row),allowed);self.assertTrue(forbidden.isdisjoint(row))
 def test_priority_and_new_source_presence(self):
  by_name={s.name:s for s in load_sources()};self.assertIn("ING",by_name);self.assertIn("Rabobank",by_name);self.assertNotIn("Uber",by_name);self.assertIn("AuditCarriere",by_name);self.assertEqual(by_name["AuditCarriere"].kind,"job_board");self.assertEqual(by_name["AuditCarriere"].official_domain,"auditcarriere.nl")
if __name__=="__main__":unittest.main()
