import unittest
from unittest.mock import patch

from scanner import REL, SENIOR, extract_jobs, listing_evidence, coverage_from_evidence, validate_jobs, job_key, qa_snapshot, api_inventory, merge_validated_jobs, discover_official_ats, airwallex_id, airwallex_official_url, strategic_inventory_match


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
                 "text":"Director Financial Crime Apply now","html":"<p>Director Financial Crime</p><a href='/apply/123'>Apply now</a>"}
        with patch("scanner.fetch",return_value=fetched):
            job=validate_jobs([candidate.copy()],set())[0]
        self.assertTrue(job["live"])
        self.assertFalse(job["board_present"])
        self.assertFalse(job["apply_live"])
        self.assertEqual(job["validation_reason"],"not_on_current_board")

    def test_live_job_passes_with_detail_and_board_proof(self):
        candidate={"title":"Director Financial Crime","url":"https://example.com/jobs/123?utm_source=test"}
        fetched={"ok":True,"final":"https://example.com/jobs/123/","status":200,
                 "text":"Director Financial Crime Apply now","html":"<p>Director Financial Crime</p><a href='/apply/123'>Apply now</a>"}
        with patch("scanner.fetch",return_value=fetched):
            job=validate_jobs([candidate.copy()],{job_key("https://example.com/jobs/123")})[0]
        self.assertTrue(job["board_present"])
        self.assertTrue(job["apply_live"])
        self.assertEqual(job["validation_reason"],"direct_live_and_current_board")

    def test_filled_job_rejects_generic_apply_cta(self):
        candidate={"title":"Director Financial Crime","url":"https://example.com/jobs/123"}
        fetched={"ok":True,"final":"https://example.com/jobs/123","status":200,
                 "text":"Director Financial Crime Apply now We're sorry, the job you are trying to apply for has been filled.",
                 "html":'<h1>Director Financial Crime</h1><a href="/apply/123">Apply now</a><p>The job you are trying to apply for has been filled.</p>'}
        with patch("scanner.fetch",return_value=fetched):
            result=validate_jobs([candidate],{job_key(candidate["url"])})[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(result["validation_reason"],"closed_marker")

    def test_apply_text_without_real_control_is_not_live(self):
        candidate={"title":"Director Financial Crime","url":"https://example.com/jobs/123"}
        fetched={"ok":True,"final":"https://example.com/jobs/123","status":200,
                 "text":"Director Financial Crime Apply now",
                 "html":"<p>Director Financial Crime Apply now</p>"}
        with patch("scanner.fetch",return_value=fetched):
            result=validate_jobs([candidate],{job_key(candidate["url"])})[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(result["validation_reason"],"no_live_apply_control")

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


class OfficialInventoryTests(unittest.TestCase):
    class Reply:
        def __init__(self, data):
            self.data=data
        def raise_for_status(self):
            return None
        def json(self):
            return self.data

    @staticmethod
    def org(name):
        return {"name":name,"official_domain":"example.com","allowed_domains":[],
                "seed_urls":["https://example.com/careers/"],"no_public_hint":False}

    def test_greenhouse_uses_official_total(self):
        url="https://job-boards.greenhouse.io/tide/jobs/"
        jobs=[{"title":"Head of Compliance","absolute_url":url+"1"},
              {"title":"Director Risk","absolute_url":url+"2"}]
        with patch("scanner.requests.get",return_value=self.Reply({"jobs":jobs,"meta":{"total":2}})):
            result=api_inventory(self.org("Tide"))
        self.assertTrue(result["complete"])
        self.assertEqual(result["official_total"],2)
        self.assertEqual(len(result["jobs"]),2)
        self.assertEqual(result["evidence_kind"],"official_api_total")

    def test_greenhouse_partial_does_not_claim_complete(self):
        url="https://job-boards.greenhouse.io/tide/jobs/1"
        payload={"jobs":[{"title":"Head of Compliance","absolute_url":url}],"meta":{"total":2}}
        with patch("scanner.requests.get",return_value=self.Reply(payload)):
            result=api_inventory(self.org("Tide"))
        self.assertFalse(result["complete"])
        self.assertEqual(result["official_total"],2)

    def test_greenhouse_foreign_employer_rejected(self):
        payload={"jobs":[{"title":"Head of Compliance",
                            "absolute_url":"https://job-boards.greenhouse.io/other/jobs/1"}],"meta":{"total":1}}
        with patch("scanner.requests.get",return_value=self.Reply(payload)):
            result=api_inventory(self.org("Tide"))
        self.assertFalse(result["complete"])
        self.assertIn("unrelated",result["error"])

    def test_lever_requires_terminal_page(self):
        jobs=[{"text":"Head of Financial Crime","hostedUrl":"https://jobs.eu.lever.co/pnlfin/job-1"},
              {"text":"Director of Risk","hostedUrl":"https://jobs.eu.lever.co/pnlfin/job-2"}]
        with patch("scanner.requests.get",return_value=self.Reply(jobs)) as get:
            result=api_inventory(self.org("Finom"))
        self.assertTrue(result["complete"])
        self.assertTrue(result["terminal"])
        self.assertIsNone(result["official_total"])
        self.assertEqual(result["evidence_kind"],"official_api_exhausted")
        self.assertEqual(get.call_args.kwargs["params"]["skip"],0)

    def test_lever_full_page_must_fetch_terminal_page(self):
        first=[{"text":f"Role {i}","hostedUrl":f"https://jobs.eu.lever.co/pnlfin/{i}"} for i in range(100)]
        with patch("scanner.requests.get",side_effect=[self.Reply(first),self.Reply([])]) as get:
            result=api_inventory(self.org("Finom"))
        self.assertTrue(result["complete"])
        self.assertEqual(get.call_count,2)
        self.assertEqual(len(result["jobs"]),100)

    def test_smartrecruiters_paginates_to_total(self):
        a={"id":"1","name":"Compliance Director"}
        b={"id":"2","name":"Head of Risk"}
        responses=[{"totalFound":2,"content":[a]},{"totalFound":2,"content":[b]}]
        with patch("scanner.requests.get",side_effect=[self.Reply(x) for x in responses]) as get:
            result=api_inventory(self.org("Varrlyn"))
        self.assertTrue(result["complete"])
        self.assertEqual(result["official_total"],2)
        self.assertEqual(get.call_count,2)
        self.assertEqual(get.call_args.kwargs["params"]["offset"],1)

    def test_smartrecruiters_inconsistent_total_fails_closed(self):
        responses=[{"totalFound":2,"content":[{"id":"1","name":"Compliance Director"}]},
                   {"totalFound":3,"content":[{"id":"2","name":"Head of Risk"}]}]
        with patch("scanner.requests.get",side_effect=[self.Reply(x) for x in responses]):
            result=api_inventory(self.org("Varrlyn"))
        self.assertFalse(result["complete"])

    def test_partial_browser_recovery_cannot_revoke_verified_match(self):
        prior={"title":"Director Risk","url":"https://example.com/jobs/1","apply_live":True,"board_present":True}
        browser={"title":"Director Risk","url":"https://example.com/jobs/1?utm_source=test","apply_live":False,
                 "board_present":False,"validation_reason":"not_on_current_board"}
        result=merge_validated_jobs([prior],[browser])
        self.assertEqual(len(result),1)
        self.assertTrue(result[0]["apply_live"])

    def test_browser_can_add_new_match_without_dropping_old(self):
        prior={"title":"Director Risk","url":"https://example.com/jobs/1","apply_live":True}
        new={"title":"Head of Audit","url":"https://example.com/jobs/2","apply_live":True}
        result=merge_validated_jobs([prior],[new])
        self.assertEqual(len(result),2)
        self.assertTrue(all(j["apply_live"] for j in result))


    def test_greenhouse_feed_discovered_only_from_official_site(self):
        org=self.org("Tide")
        official={"final":"https://example.com/careers/","html":'<a href="https://job-boards.greenhouse.io/tide">Open positions</a>'}
        untrusted={"final":"https://unrelated.example.org/article",
                   "html":'<a href="https://job-boards.greenhouse.io/othercompany">Jobs</a>'}
        found=discover_official_ats([untrusted,official],org)
        self.assertEqual([x["url"] for x in found],
                         ["https://boards-api.greenhouse.io/v1/boards/tide/jobs"])

    def test_eu_greenhouse_link_keeps_eu_region(self):
        org=self.org("Surepay")
        page={"final":"https://example.com/careers/",
              "html":'<a href="https://job-boards.eu.greenhouse.io/surepay">Vacancies</a>'}
        found=discover_official_ats([page],org)
        self.assertEqual(found[0]["url"],"https://boards-api.eu.greenhouse.io/v1/boards/surepay/jobs")

    def test_authoritative_lever_seed_can_be_discovered(self):
        org=self.org("Finom")
        org["seed_urls"]=["https://jobs.eu.lever.co/pnlfin/"]
        page={"final":"https://jobs.eu.lever.co/pnlfin/","html":"<p>Official board</p>"}
        found=discover_official_ats([page],org)
        self.assertEqual(found[0]["url"],"https://api.eu.lever.co/v0/postings/pnlfin")


class AirwallexDiscoveryTests(unittest.TestCase):
    AML="ad877e85-6c71-4e6b-afc7-3d87b9488adb"
    MLRO="15a5d8b4-a5fd-4b4d-a933-387702221b75"
    EXPIRED="004af48d-83e6-44c0-9ed0-493142195481"

    @staticmethod
    def org():
        return {"name":"Airwallex","official_domain":"airwallex.com","allowed_domains":[],
                "seed_urls":["https://careers.airwallex.com/jobs/"],"no_public_hint":False}

    @classmethod
    def posting(cls, title, identifier, location="UK - London", listed=True):
        return {"id":identifier,"title":title,"jobUrl":"https://jobs.ashbyhq.com/airwallex/"+identifier,
                "location":location,"department":"Regulatory & Compliance",
                "team":"Financial Crime Compliance","isListed":listed,"publishedAt":"2026-09-28"}

    def test_two_real_strategic_vacancies_are_discovered(self):
        data={"apiVersion":"1","jobs":[
            self.posting("Senior Director, AML & Sanctions, Governance & Policy",self.AML),
            self.posting("Senior Director EU & ME, MLRO",self.MLRO,"NL - Amsterdam"),
            self.posting("Senior Software Engineer", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",listed=False)]}
        with patch("scanner.requests.get",return_value=OfficialInventoryTests.Reply(data)):
            feed=api_inventory(self.org())
        self.assertTrue(feed["complete"])
        self.assertEqual(feed["official_total"],2)
        self.assertEqual(len(feed["jobs"]),2)
        by_id={j["source_job_id"]:j for j in feed["jobs"]}
        self.assertEqual(set(by_id),{self.AML,self.MLRO})
        self.assertTrue(all(strategic_inventory_match(j) for j in feed["jobs"]))
        self.assertEqual(by_id[self.MLRO]["location"],"NL - Amsterdam")
        self.assertEqual(by_id[self.AML]["url"],
                         "https://careers.airwallex.com/job/"+self.AML+
                         "/senior-director-aml-sanctions-governance-policy/")

    def test_expired_ashby_link_is_not_discovered(self):
        data={"apiVersion":"1","jobs":[self.posting("Senior Director EU & ME, MLRO",self.MLRO)]}
        with patch("scanner.requests.get",return_value=OfficialInventoryTests.Reply(data)):
            feed=api_inventory(self.org())
        self.assertTrue(feed["complete"])
        self.assertNotIn(self.EXPIRED,{j["source_job_id"] for j in feed["jobs"]})

    def test_ashby_only_posting_needs_matching_first_party_detail_and_apply(self):
        candidate=self.posting("Senior Director, AML & Sanctions, Governance & Policy",self.AML)
        u=airwallex_official_url(candidate)
        job={"title":candidate["title"],"url":u,"source_job_id":self.AML}
        fetched={"ok":True,"final":u,"status":200,"text":candidate["title"]+" Submit application",
                 "html":"<h1>"+candidate["title"]+"</h1><form><button type='submit'>Submit application</button></form>"}
        with patch("scanner.fetch",return_value=fetched):
            accepted=validate_jobs([job],{job_key(u)})[0]
            unlisted=validate_jobs([job],set())[0]
        self.assertTrue(accepted["apply_live"])
        self.assertFalse(unlisted["apply_live"])
        self.assertEqual(unlisted["validation_reason"],"not_on_current_board")

    def test_wrong_job_redirect_cannot_pass_with_matching_title_and_apply(self):
        candidate=self.posting("Senior Director, AML & Sanctions, Governance & Policy",self.AML)
        u=airwallex_official_url(candidate)
        changed=u.replace(self.AML,self.MLRO)
        job={"title":candidate["title"],"url":u,"source_job_id":self.AML}
        fetched={"ok":True,"final":changed,"status":200,"text":candidate["title"]+" Submit application",
                 "html":"<h1>"+candidate["title"]+"</h1><button>Submit application</button>"}
        with patch("scanner.fetch",return_value=fetched):
            result=validate_jobs([job],{job_key(u)})[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(result["validation_reason"],"detail_page_not_live")

    def test_unlisted_or_unrelated_provider_entries_cannot_prove_full_inventory(self):
        good=self.posting("Senior Director EU & ME, MLRO",self.MLRO,listed=False)
        bad=self.posting("Director, Risk",self.AML)
        bad["jobUrl"]=bad["jobUrl"].replace("/airwallex/","/othercompany/")
        data={"apiVersion":"1","jobs":[good,bad]}
        with patch("scanner.requests.get",return_value=OfficialInventoryTests.Reply(data)):
            feed=api_inventory(self.org())
        self.assertFalse(feed["complete"])
        self.assertEqual(feed["official_total"],1)

    def test_broad_department_recognizes_nonliteral_strategic_role(self):
        candidate={"title":"Chief Policy Architect","department":"Regulatory & Compliance","team":"Financial Crime Compliance"}
        self.assertTrue(strategic_inventory_match(candidate))
        self.assertFalse(strategic_inventory_match({"title":"Account Executive","department":"Sales","team":"Commercial"}))


if __name__ == "__main__":
    unittest.main()
