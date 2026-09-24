import unittest
from unittest.mock import patch

from scanner import REL, SENIOR, extract_jobs, listing_evidence, coverage_from_evidence, validate_jobs, job_key, qa_snapshot


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
        html = '5 jobs' + ''.join(f'<a href="/jobs/{i}">Director Risk {i}</a>' for i in range(1,6))
        evidence = listing_evidence(page(html), ORG)
        self.assertTrue(evidence["static_complete_evidence"])
        self.assertEqual(coverage_from_evidence([evidence], {**ORG,"no_public_hint":False}), "verified_complete")

    def test_verified_no_public_board_is_distinct(self):
        evidence = listing_evidence(page("<p>Executive search mandates are confidential.</p>"), ORG)
        self.assertEqual(coverage_from_evidence([evidence], {**ORG,"no_public_hint":True}), "verified_no_public_board")


    def test_live_job_requires_current_board_presence(self):
        candidate={"title":"Director Financial Crime","url":"https://example.com/jobs/123"}
        fetched={"ok":True,"final":"https://example.com/jobs/123","status":200,
                 "text":"Director Financial Crime Apply now","html":"<p>Director Financial Crime Apply now</p>"}
        with patch("scanner.fetch",return_value=fetched):
            job=validate_jobs([candidate.copy()],set())[0]
        self.assertTrue(job["live"])
        self.assertFalse(job["board_present"])
        self.assertFalse(job["apply_live"])
        self.assertEqual(job["validation_reason"],"not_on_current_board")

    def test_live_job_passes_with_detail_and_board_proof(self):
        candidate={"title":"Director Financial Crime","url":"https://example.com/jobs/123?utm_source=test"}
        fetched={"ok":True,"final":"https://example.com/jobs/123/","status":200,
                 "text":"Director Financial Crime Apply now","html":"<p>Director Financial Crime Apply now</p>"}
        with patch("scanner.fetch",return_value=fetched):
            job=validate_jobs([candidate.copy()],{job_key("https://example.com/jobs/123")})[0]
        self.assertTrue(job["board_present"])
        self.assertTrue(job["apply_live"])
        self.assertEqual(job["validation_reason"],"direct_live_and_current_board")

    def test_snapshot_qa_rejects_false_live_record(self):
        payload={"organisations":[{"name":"Example","jobs":[{"title":"Risk Director","url":"https://example.com/jobs/1",
                  "apply_live":True,"live":True,"board_present":False,"http_status":200}]}],
                 "live_relevant_jobs":[]}
        with self.assertRaises(RuntimeError):
            qa_snapshot(payload)

    def test_snapshot_qa_accepts_dual_verified_live_record(self):
        job={"title":"Risk Director","url":"https://example.com/jobs/1","apply_live":True,
             "live":True,"board_present":True,"http_status":200}
        payload={"organisations":[{"name":"Example","jobs":[job.copy()]}],
                 "live_relevant_jobs":[{"organisation":"Example",**job}]}
        qa=qa_snapshot(payload)
        self.assertTrue(qa["passed"])
        self.assertEqual(qa["live_jobs_checked"],1)


if __name__ == "__main__":
    unittest.main()
