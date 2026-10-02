import unittest
from probe_rabobank import parse_inventory

HTML = """<html><body><h1>3 Vacatures bij Rabobank</h1><a href="/nl/vacature/a/JR_00000001/">A</a><a href="/nl/vacature/b/JR_00000002/">B</a><a href="/nl/vacature/c/JR_00000003/">C</a></body></html>"""

class RabobankInventoryTests(unittest.TestCase):
    def test_reconciles_exact_first_party_total(self):
        r=parse_inventory(HTML,"https://rabobank.jobs/nl/vacatures/")
        self.assertEqual(r["official_total"],3)
        self.assertEqual(r["unique_count"],3)
        self.assertTrue(r["complete"])

    def test_fails_closed_when_listing_is_partial(self):
        r=parse_inventory(HTML.replace("3 Vacatures","4 Vacatures"),"https://rabobank.jobs/nl/vacatures/")
        self.assertEqual(r["official_total"],4)
        self.assertEqual(r["unique_count"],3)
        self.assertFalse(r["complete"])

if __name__=="__main__":
    unittest.main()
