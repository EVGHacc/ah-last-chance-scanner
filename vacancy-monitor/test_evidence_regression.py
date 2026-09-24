import unittest
import scanner

class EvidenceRegression(unittest.TestCase):
    def setUp(self):
        self.org={"official_domain":"vroomsearch.com","allowed_domains":[],"no_public_hint":False}
    def evidence(self, prefix=""):
        return scanner.listing_evidence({"final":"https://vroomsearch.com/nl/vacatures", "html":prefix+'<a href="/nl/vacature/head-compliance">Head of Compliance</a>'},self.org)
    def test_search_hostname_is_not_navigation(self):
        self.assertEqual(self.evidence()["job_link_count"],1)
    def test_unknown_total_is_not_proof(self):
        self.assertFalse(self.evidence()["static_complete_evidence"])
    def test_matching_official_total(self):
        self.assertTrue(self.evidence("1 vacature")["static_complete_evidence"])
    def test_incomplete_total(self):
        self.assertFalse(self.evidence("12 vacatures")["static_complete_evidence"])
    def test_unreachable_search_firm_not_no_board_proof(self):
        self.assertEqual(scanner.coverage_from_evidence([],{"no_public_hint":True}),"unproven")
    def test_research_title_not_excluded(self):
        self.assertTrue(scanner.inventory_url("https://example.com/job/director-governance-research/"))
    def test_privacy_navigation_excluded(self):
        self.assertFalse(scanner.inventory_url("https://example.com/careers/cookie-policy"))

if __name__ == "__main__":
    unittest.main()
