import unittest

from scanner import REL, SENIOR, extract_jobs, listing_evidence, coverage_from_evidence


ORG = {"official_domain": "example.com", "allowed_domains": []}


def page(body):
    return {"html": body, "final": "https://example.com/careers/jobs"}


class ScannerTests(unittest.TestCase):
    def test_role_boundaries_and_seniority(self):
        self.assertIsNotNone(REL.search("Group MLRO"))
        self.assertIsNotNone(SENIOR.search("VP Business Control"))
        self.assertIsNotNone(REL.search("Business Resilience Officer"))
        self.assertIsNotNone(SENIOR.search("Business Resilience Officer – Operational Continuity"))
        self.assertIsNotNone(REL.search("Head of Financial Intelligence"))
        self.assertIsNotNone(REL.search("Non-Financial Risk Oversight"))
        self.assertIsNotNone(SENIOR.search("Senior Compliance Officer"))

    def test_job_cards_and_structured_posting(self):
        html = '''<a href="/jobs/123">Director Financial Crime</a>
        <script type="application/ld+json">{"@type":"JobPosting","title":"Head of Internal Audit","url":"https://example.com/opportunities/456"}</script>'''
        jobs = extract_jobs(page(html), ORG)
        self.assertEqual({j["title"] for j in jobs}, {"Director Financial Crime", "Head of Internal Audit"})

    def test_listing_is_partial_when_next_page_exists(self):
        html = '<a href="/jobs/123">Director Financial Crime</a><a href="?page=2">Next</a>'
        evidence = listing_evidence(page(html), ORG)
        self.assertEqual(evidence["job_link_count"], 1)
        self.assertTrue(evidence["pagination_seen"])
        self.assertFalse(evidence["static_complete_evidence"])

    def test_static_listing_can_prove_complete_inventory(self):
        html = ''.join(f'<a href="/jobs/{i}">Director Risk {i}</a>' for i in range(1,6))
        evidence = listing_evidence(page(html), ORG)
        self.assertTrue(evidence["static_complete_evidence"])
        self.assertEqual(coverage_from_evidence([evidence], {**ORG,"no_public_hint":False}), "verified_complete")

    def test_verified_no_public_board_is_distinct(self):
        evidence = listing_evidence(page("<p>Executive search mandates are confidential.</p>"), ORG)
        self.assertEqual(coverage_from_evidence([evidence], {**ORG,"no_public_hint":True}), "verified_no_public_board")


if __name__ == "__main__":
    unittest.main()
