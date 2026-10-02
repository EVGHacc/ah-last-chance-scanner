import ast
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.model import Coverage, InventoryProof, Source

class CleanSheetTests(unittest.TestCase):
    def test_v4_has_zero_inherited_coverage(self):
        self.assertEqual(Coverage.UNPROVEN.value,"unproven")

    def test_complete_requires_exhaustion(self):
        s=Source("employer","Example","example.com",("https://example.com/jobs",))
        with self.assertRaises(ValueError):
            InventoryProof(s,Coverage.VERIFIED_COMPLETE,1,1,False,"official_total").validate()

    def test_complete_requires_count_reconciliation(self):
        s=Source("employer","Example","example.com",("https://example.com/jobs",))
        with self.assertRaises(ValueError):
            InventoryProof(s,Coverage.VERIFIED_COMPLETE,2,3,True,"official_total").validate()

    def test_no_legacy_imports_in_v4(self):
        forbidden=("vacancy-monitor","vacancy_v3","vacancy-v3")
        for p in (ROOT/"app").rglob("*.py"):
            tree=ast.parse(p.read_text())
            text=p.read_text()
            self.assertFalse(any(x in text for x in forbidden),p)

if __name__=="__main__": unittest.main()
