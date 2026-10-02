import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"vacancy-v3"))

from app.models import InventoryProof
from app.registry import load_registry


class FoundationTests(unittest.TestCase):
    def test_current_registry_is_106_unique_sources(self):
        sources=load_registry(ROOT/"vacancy-monitor"/"registry.tsv")
        self.assertEqual(106,len(sources))
        self.assertEqual(106,len({(x.kind,x.name) for x in sources}))

    def test_authoritative_total_must_reconcile(self):
        self.assertTrue(InventoryProof("x","api",4,4,4,True,0).verified_complete)
        self.assertFalse(InventoryProof("x","api",6,6,4,True,0).verified_complete)

    def test_exhaustion_can_prove_source_without_total(self):
        self.assertTrue(InventoryProof("x","lever",3,3,None,True,0).verified_complete)
        self.assertFalse(InventoryProof("x","lever",3,3,None,False,0).verified_complete)

    def test_duplicates_and_errors_fail_closed(self):
        self.assertFalse(InventoryProof("x","api",4,3,3,True,1).verified_complete)
        self.assertFalse(InventoryProof("x","api",3,3,3,True,0,"timeout").verified_complete)


if __name__ == "__main__":
    unittest.main()
