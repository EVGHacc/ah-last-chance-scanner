import json
import unittest
from unittest.mock import patch

from embedded_inventory import embedded_inventory
from scanner import REL, SENIOR, extract_jobs, listing_evidence, coverage_from_evidence, validate_jobs, job_key, qa_snapshot, api_inventory, merge_validated_jobs, discover_official_ats, airwallex_id, airwallex_official_url, strategic_inventory_match, airwallex_validation_queue, validate_workday_candidate, airwallex_id, airwallex_official_url, strategic_inventory_match, validate_wise_candidate


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

    def test_coinmerce_overview_discovers_group_ccro(self):
        org={"name":"Coinmerce","official_domain":"coinmerce.io",
             "allowed_domains":["coinmerce.jobs.personio.com"],
             "seed_urls":["https://careers.coinmerce.io/en/overview"],
             "no_public_hint":False}
        html=('Vacancies (8)<a href="/en/overview/2503505">'
              'Chief Compliance & Risk Officer</a>')
        page={"html":html,"final":"https://careers.coinmerce.io/en/overview"}
        found=extract_jobs(page,org)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["title"],"Chief Compliance & Risk Officer")
        self.assertEqual(found[0]["url"],"https://careers.coinmerce.io/en/overview/2503505")
        self.assertEqual(listing_evidence(page,org)["job_link_count"],1)

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

    def test_greenhouse_exhausted_feed_without_optional_meta(self):
        url="https://job-boards.greenhouse.io/tide/jobs/"
        jobs=[{"title":"Head of Compliance","absolute_url":url+"1"},
              {"title":"Director Risk","absolute_url":url+"2"}]
        with patch("scanner.requests.get",return_value=self.Reply({"jobs":jobs})):
            result=api_inventory(self.org("Tide"))
        self.assertTrue(result["complete"])
        self.assertTrue(result["terminal"])
        self.assertIsNone(result["official_total"])
        self.assertEqual(result["evidence_kind"],"official_api_exhausted")
        self.assertEqual(len(result["jobs"]),2)

    def test_greenhouse_missing_meta_does_not_accept_empty_or_malformed_feed(self):
        url="https://job-boards.greenhouse.io/tide/jobs/1"
        payloads=[{"jobs":[]},
                  {"jobs":[{"title":"Director Risk"}]},
                  {"jobs":[{"title":"Director Risk","absolute_url":url},
                           {"title":"Director Risk","absolute_url":url}]}]
        for payload in payloads:
            with self.subTest(payload=payload):
                with patch("scanner.requests.get",return_value=self.Reply(payload)):
                    self.assertFalse(api_inventory(self.org("Tide"))["complete"])

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


class AirwallexCoverageTests(unittest.TestCase):
    """Regression cases for the 2026-09-29 missed senior Airwallex roles."""
    AML_ID="ad877e85-6c71-4e6b-afc7-3d87b9488adb"
    MLRO_ID="15a5d8b4-a5fd-4b4d-a933-387702221b75"
    OLD_ID="004af48d-83e6-44c0-9ed0-493142195481"

    @staticmethod
    def org():
        return {"name":"Airwallex","official_domain":"airwallex.com",
                "allowed_domains":[],"seed_urls":["https://careers.airwallex.com/jobs/"],
                "no_public_hint":False}

    @staticmethod
    def posting(ident,title,listed=True,location="UK - London",
                dept="Regulatory & Compliance",team="Financial Crime Compliance"):
        return {"id":ident,"title":title,
                "jobUrl":f"https://jobs.ashbyhq.com/airwallex/{ident}",
                "applyUrl":f"https://jobs.ashbyhq.com/airwallex/{ident}/application",
                "isListed":listed,"location":location,"department":dept,
                "team":team}

    def test_ashby_feed_recovers_aml_and_mlro_but_rejects_old_unlisted_risk_assurance(self):
        data={"apiVersion":"1","jobs":[
            self.posting(self.AML_ID,"Senior Director, AML & Sanctions, Governance & Policy"),
            self.posting(self.MLRO_ID,"Senior Director EU & ME, MLRO",
                         location="NL - Amsterdam"),
            self.posting(self.OLD_ID,"Senior Director of Risk Assurance (Monitoring Framework & Reporting)",False)]}
        with patch("scanner.requests.get",return_value=OfficialInventoryTests.Reply(data)):
            inv=api_inventory(self.org())
        self.assertTrue(inv["complete"])
        self.assertEqual(inv["official_total"],2)
        self.assertEqual(len(inv["jobs"]),2)
        self.assertEqual({j["source_job_id"] for j in inv["jobs"]},{self.AML_ID,self.MLRO_ID})
        self.assertTrue(all(j["url"].startswith("https://careers.airwallex.com/job/") for j in inv["jobs"]))
        self.assertTrue(all(strategic_inventory_match(j) for j in inv["jobs"]))
        self.assertEqual(inv["jobs"][0]["url"],"https://careers.airwallex.com/job/"+
                         self.AML_ID+"/senior-director-aml-sanctions-governance-policy/")

    def test_ashby_identity_mismatch_fails_closed(self):
        item=self.posting(self.AML_ID,"Senior Director AML Policy")
        item["id"]=self.MLRO_ID
        with patch("scanner.requests.get",return_value=OfficialInventoryTests.Reply(
                {"apiVersion":"1","jobs":[item]})):
            inv=api_inventory(self.org())
        self.assertFalse(inv["complete"])
        self.assertEqual(inv["jobs"],[])

    def test_ashby_no_jobs_does_not_prove_complete(self):
        with patch("scanner.requests.get",return_value=OfficialInventoryTests.Reply(
                {"apiVersion":"1","jobs":[]})):
            self.assertFalse(api_inventory(self.org())["complete"])

    def test_senior_governance_detected_from_department_when_title_is_unusual(self):
        j={"title":"Director, Platform Policy","department":"Regulatory & Compliance",
           "team":"Financial Crime Compliance"}
        self.assertTrue(strategic_inventory_match(j))
        self.assertFalse(strategic_inventory_match({**j,"title":"Junior Analyst"}))
        self.assertFalse(strategic_inventory_match({"title":"Senior Engineering Manager",
                                                     "department":"Technology","team":"Engineering"}))

    def test_first_party_and_board_and_apply_are_all_required(self):
        candidate={"title":"Senior Director, AML & Sanctions, Governance & Policy",
                   "url":"https://careers.airwallex.com/job/"+self.AML_ID+
                         "/senior-director-aml-sanctions-governance-policy/",
                   "source_job_id":self.AML_ID}
        response={"ok":True,"final":candidate["url"],"status":200,
                  "html":"<title>Senior Director, AML & Sanctions, Governance & Policy</title>"
                         "<h1>Senior Director, AML & Sanctions, Governance & Policy</h1>"
                         '<button type="submit">Submit application</button>',
                  "text":"Senior Director, AML & Sanctions, Governance & Policy Submit application"}
        with patch("scanner.fetch",return_value=response):
            j=validate_jobs([candidate],{job_key(candidate["url"])})[0]
            self.assertTrue(j["apply_live"])
            self.assertTrue(j["board_present"])
            j2=validate_jobs([candidate],set())[0]
            self.assertFalse(j2["apply_live"])
            self.assertEqual(j2["validation_reason"],"not_on_current_board")

    def test_old_direct_page_is_not_live_without_active_ats_board(self):
        candidate={"title":"Senior Director of Risk Assurance",
                   "url":"https://careers.airwallex.com/job/"+self.OLD_ID+"/risk-assurance/",
                   "source_job_id":self.OLD_ID}
        response={"ok":True,"final":candidate["url"],"status":200,
                  "html":"<h1>Senior Director of Risk Assurance</h1>"
                         '<button type="submit">Submit application</button>',
                  "text":"Senior Director of Risk Assurance Submit application"}
        with patch("scanner.fetch",return_value=response):
            j=validate_jobs([candidate],set())[0]
        self.assertFalse(j["apply_live"])

    def test_first_party_redirect_to_different_job_id_is_not_live(self):
        candidate={"title":"Senior Director, AML & Sanctions, Governance & Policy",
                   "url":"https://careers.airwallex.com/job/"+self.AML_ID+"/role/",
                   "source_job_id":self.AML_ID}
        response={"ok":True,"final":"https://careers.airwallex.com/job/"+self.MLRO_ID+"/other/",
                  "status":200,"html":'<button type="submit">Submit application</button>',
                  "text":candidate["title"]}
        with patch("scanner.fetch",return_value=response):
            j=validate_jobs([candidate],{job_key(candidate["url"])})[0]
        self.assertFalse(j["apply_live"])
        self.assertEqual(j["validation_reason"],"detail_page_not_live")


    def test_priority_queue_retains_all_candidates_and_selects_both_strong_roles(self):
        critical=[{"title":"Senior Director, AML & Sanctions, Governance & Policy",
                   "location":"UK - London","source_job_id":self.AML_ID,
                   "url":"https://careers.airwallex.com/job/"+self.AML_ID+"/senior-director-aml-sanctions-governance-policy/"},
                  {"title":"Senior Director EU & ME, MLRO","location":"NL - Amsterdam",
                   "source_job_id":self.MLRO_ID,
                   "url":"https://careers.airwallex.com/job/"+self.MLRO_ID+"/senior-director-eu-me-mlro/"}]
        others=[{"title":"Manager, Regulatory Operations","location":"Singapore",
                 "source_job_id":str(i),"url":"https://careers.airwallex.com/job/"+str(i)+"/"} for i in range(50)]
        chosen,pending=airwallex_validation_queue(critical+others,capacity=25,priority_count=20)
        self.assertEqual(len(chosen),25)
        self.assertEqual(len(pending),27)
        self.assertTrue({self.AML_ID,self.MLRO_ID}.issubset({j["source_job_id"] for j in chosen}))
        self.assertTrue(all(not j["apply_live"] and j["validation_reason"]=="pending_direct_validation"
                            for j in pending))
        self.assertEqual(len({j["source_job_id"] for j in chosen+pending}),52)

    def test_rate_limited_detail_is_not_reportable(self):
        candidate=self.posting(self.AML_ID,"Senior Director, AML & Sanctions, Governance & Policy")
        u=airwallex_official_url(candidate)
        j={"title":candidate["title"],"url":u,"source_job_id":self.AML_ID}
        fetched={"ok":False,"final":u,"status":429,"text":"",
                 "html":"<button>Submit application</button>"}
        with patch("scanner.fetch",return_value=fetched):
            result=validate_jobs([j],{job_key(u)})[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(result["validation_reason"],"rate_limited")


class VisaWorkdayTests(unittest.TestCase):
    class Reply:
        def __init__(self,data=None,status_code=200,url=""):
            self.data=data or {};self.status_code=status_code;self.url=url
        def raise_for_status(self):
            if self.status_code>=400:raise RuntimeError("HTTP "+str(self.status_code))
        def json(self):return self.data

    @staticmethod
    def org():
        return {"name":"Visa","official_domain":"visa.com",
                "allowed_domains":[],"seed_urls":["https://corporate.visa.com/en/jobs/"],
                "no_public_hint":False}

    @staticmethod
    def posting(i):
        return {"title":f"Director, Risk Governance {i}",
                "externalPath":f"/job/GB---London-United-Kingdom/Director--Risk-Governance_{'REF%06dW' % i}"}

    def test_workday_continuation_total_zero_is_valid_only_if_exhausted(self):
        first={"total":21,"jobPostings":[self.posting(i) for i in range(20)]}
        second={"total":0,"jobPostings":[self.posting(20)]}
        with patch("scanner.requests.post",side_effect=[self.Reply(first),self.Reply(second)]) as post:
            inv=api_inventory(self.org())
        self.assertTrue(inv["complete"])
        self.assertEqual(inv["official_total"],21)
        self.assertEqual(len(inv["jobs"]),21)
        self.assertEqual(post.call_count,2)
        self.assertEqual(inv["jobs"][20]["workday_job_id"],"REF000020W")
        self.assertEqual(inv["jobs"][20]["workday_detail_url"],
                         "https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa"+
                         self.posting(20)["externalPath"])

    def test_workday_partial_or_duplicate_continuation_is_not_proven(self):
        first={"total":21,"jobPostings":[self.posting(i) for i in range(20)]}
        with patch("scanner.requests.post",side_effect=[
                self.Reply(first),self.Reply({"total":0,"jobPostings":[]})]):
            self.assertFalse(api_inventory(self.org())["complete"])
        with patch("scanner.requests.post",side_effect=[
                self.Reply(first),self.Reply({"total":0,"jobPostings":[self.posting(0)]})]):
            self.assertFalse(api_inventory(self.org())["complete"])
        with patch("scanner.requests.post",side_effect=[
                self.Reply(first),self.Reply({"total":22,"jobPostings":[self.posting(20)]})]):
            self.assertFalse(api_inventory(self.org())["complete"])

    @staticmethod
    def candidate():
        path="/job/GB---London-United-Kingdom/Director--Rules-Governance-and-Transformation_REF088281W"
        board="https://visa.wd5.myworkdayjobs.com/Visa"
        return {"title":"Director, Rules Governance and Transformation",
                "url":board+path,
                "workday_detail_url":"https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa"+path,
                "workday_job_id":"REF088281W"}

    def test_exact_official_workday_detail_can_apply_and_route(self):
        j=self.candidate()
        data={"jobPostingInfo":{"title":j["title"],"jobReqId":"REF088281W",
                "canApply":True,"externalUrl":j["url"]}}
        apply_url=j["url"]+"/apply"
        with patch("scanner.requests.get",side_effect=[
            self.Reply(data,200,j["workday_detail_url"]),
            self.Reply({},200,apply_url)]) as req:
            result=validate_jobs([j],{job_key(j["url"])})[0]
        self.assertTrue(result["apply_live"])
        self.assertTrue(result["board_present"])
        self.assertEqual(result["validation_reason"],"direct_live_and_current_board")
        self.assertEqual(result["apply_url"],apply_url)
        self.assertEqual(req.call_count,2)

    def test_workday_closed_or_wrong_identity_never_passes(self):
        j=self.candidate()
        for changed in ({"canApply":False},{"jobReqId":"REF000001W"},
                        {"title":"Unrelated Director"},
                        {"externalUrl":"https://visa.wd5.myworkdayjobs.com/Visa/job/unrelated"}):
            info={"title":j["title"],"jobReqId":"REF088281W","canApply":True,
                  "externalUrl":j["url"]}
            info.update(changed)
            with patch("scanner.requests.get",return_value=
                    self.Reply({"jobPostingInfo":info},200,j["workday_detail_url"])) as get:
                result=validate_jobs([j],{job_key(j["url"])})[0]
            self.assertFalse(result["apply_live"])
            self.assertEqual(get.call_count,1)
        with patch("scanner.requests.get",return_value=
                self.Reply({"jobPostingInfo":{"title":j["title"],"jobReqId":"REF088281W",
                "canApply":True,"externalUrl":j["url"]}},200,j["workday_detail_url"])) as get:
            result=validate_jobs([j],set())[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(get.call_count,1)

    def test_workday_apply_redirect_does_not_count_as_application_route(self):
        j=self.candidate()
        info={"jobPostingInfo":{"title":j["title"],"jobReqId":"REF088281W",
                                  "canApply":True,"externalUrl":j["url"]}}
        with patch("scanner.requests.get",side_effect=[
                self.Reply(info,200,j["workday_detail_url"]),
                self.Reply({},200,"https://visa.wd5.myworkdayjobs.com/Visa")]):
            result=validate_jobs([j],{job_key(j["url"])})[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(result["validation_reason"],"no_live_apply_control")


class FirstPartyEmbeddedIndexTests(unittest.TestCase):
    N26_ID="7845376"
    UK_ID="6777d9e3-caf3-48e0-93ef-80e39230b1c7"
    EU_ID="34647acd-dc06-4897-a30a-f1cca93abc87"
    GOV_ID="158b9187-b51d-4674-9409-510565ca8a3b"

    @staticmethod
    def n26_page(count=1):
        raw='["title","Team Lead Non-Financial Risk and Internal Controls","id",7845376,"2026-08-05T05:59:35-04:00"]'
        return ('<h1>Search from '+str(count)+' positions to find your new careers path</h1>'
                '<script>window.__reactRouterContext.streamController.enqueue('+
                json.dumps(raw)+');</script>')

    @staticmethod
    def revolut_page(count=3):
        ids=(FirstPartyEmbeddedIndexTests.UK_ID,FirstPartyEmbeddedIndexTests.EU_ID,
             FirstPartyEmbeddedIndexTests.GOV_ID)
        titles=("Head of Financial Crime & Fraud Risk",
                "Head of Financial Crime & Fraud Risk",
                "Financial Crime Compliance Governance Manager")
        jobs=[{"id":ident,"text":title,"team":"Risk, Compliance & Audit",
               "locations":[{"name":"UK - Remote","type":"remote","country":"United Kingdom"}]}
              for ident,title in zip(ids,titles)]
        data={"props":{"pageProps":{"positions":jobs}}}
        return ('<h1>We have '+str(count)+' open positions</h1>'
                '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>')

    def test_n26_unseen_title_and_id_comes_from_first_party_embedded_index(self):
        x=embedded_inventory("N26",self.n26_page(),"https://n26.com/en-eu/careers")
        self.assertTrue(x["complete"])
        self.assertEqual(x["official_total"],1)
        self.assertEqual(x["jobs"][0]["embedded_job_id"],self.N26_ID)
        self.assertEqual(x["jobs"][0]["url"],"https://n26.com/en-eu/careers/positions/7845376")
        self.assertTrue(strategic_inventory_match(x["jobs"][0]))

    def test_n26_partial_source_remains_partial_but_keeps_candidate(self):
        x=embedded_inventory("N26",self.n26_page(63),"https://n26.com/en-eu/careers")
        self.assertFalse(x["complete"])
        self.assertEqual(x["official_total"],63)
        self.assertEqual(len(x["jobs"]),1)

    def test_revolut_two_identically_titled_heads_are_separate_and_governance_recovers(self):
        x=embedded_inventory("Revolut",self.revolut_page(),"https://www.revolut.com/careers/")
        self.assertTrue(x["complete"])
        self.assertEqual(len(x["jobs"]),3)
        ids={j["embedded_job_id"] for j in x["jobs"]}
        self.assertEqual(ids,{self.UK_ID,self.EU_ID,self.GOV_ID})
        self.assertTrue(all(strategic_inventory_match(j) for j in x["jobs"]))
        heads=[j for j in x["jobs"] if j["title"].startswith("Head")]
        self.assertEqual(len({j["url"] for j in heads}),2)
        self.assertIn("head-of-financial-crime-fraud-risk-"+self.EU_ID,heads[1]["url"])

    def test_revolut_missing_or_truncated_index_never_proves_complete(self):
        x=embedded_inventory("Revolut",self.revolut_page(4),"https://www.revolut.com/careers/")
        self.assertFalse(x["complete"])
        x=embedded_inventory("Revolut","<h1>We have 3 open positions</h1>",
                             "https://www.revolut.com/careers/")
        self.assertFalse(x["complete"])
        self.assertEqual(x["jobs"],[])

    def test_revolut_only_exact_official_detail_and_own_apply_form_pass(self):
        candidate=embedded_inventory("Revolut",self.revolut_page(),"https://www.revolut.com/careers/")["jobs"][0]
        ident=candidate["embedded_job_id"]
        apply_url="https://www.revolut.com/careers/apply/"+ident+"/"
        detail={"ok":True,"final":candidate["url"],"status":200,
                "html":'<h1>Head of Financial Crime & Fraud Risk</h1>'
                       '<a href="/careers/apply/'+ident+'/">Apply for this role</a>',
                "text":"Head of Financial Crime & Fraud Risk Apply for this role"}
        form={"ok":True,"final":apply_url,"status":200,
              "html":'<h1>Apply</h1><form><input name="firstName"></form>'+ident,
              "text":"Apply"}
        with patch("scanner.fetch",side_effect=[detail,form]) as fetched:
            result=validate_jobs([candidate],{job_key(candidate["url"])})[0]
        self.assertTrue(result["apply_live"])
        self.assertEqual(result["validation_reason"],"direct_live_and_current_board")
        self.assertEqual(fetched.call_count,2)
        with patch("scanner.fetch",side_effect=[detail,{**form,"final":"https://www.revolut.com/careers/"}]):
            result=validate_jobs([candidate],{job_key(candidate["url"])})[0]
        self.assertFalse(result["apply_live"])
        with patch("scanner.fetch",return_value=detail) as fetched:
            result=validate_jobs([candidate],set())[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(fetched.call_count,1)

    def test_n26_live_apply_route_can_be_react_rendered_without_static_html_form(self):
        candidate=embedded_inventory("N26",self.n26_page(),"https://n26.com/en-eu/careers")["jobs"][0]
        ident=candidate["embedded_job_id"]
        apply_url=candidate["url"]+"/apply"
        detail={"ok":True,"final":candidate["url"],"status":200,
                "html":'<h1>'+candidate["title"]+'</h1>'
                       '<a href="/en-eu/careers/positions/'+ident+'/apply">Apply for this position</a>',
                "text":candidate["title"]}
        form={"ok":True,"final":apply_url,"status":200,
              "html":'<title>Apply as a '+candidate["title"]+' at N26</title>'+ident,
              "text":candidate["title"]}
        with patch("scanner.fetch",side_effect=[detail,form]):
            result=validate_jobs([candidate],{job_key(candidate["url"])})[0]
        self.assertTrue(result["apply_live"])
        with patch("scanner.fetch",side_effect=[detail,{**form,"status":404,"ok":False}]):
            result=validate_jobs([candidate],{job_key(candidate["url"])})[0]
        self.assertFalse(result["apply_live"])


class WisePublicATSRegressionTests(unittest.TestCase):
    IDS={
        "Compliance Lead (Wise Platform)":("744000145714264","a9d42bdf-1da9-47df-b2dc-fb2a8156416b"),
        "Compliance Manager: Group Regulatory Compliance":("744000141493699","b7061501-45d0-4e4e-b1cb-b5a9826d2f55"),
        "Senior Risk Manager":("744000141874569","be4296e6-6375-42a4-8ffc-f63099a2410f"),
        "Group Lead - Assets Risk":("744000139018719","32871e47-8380-425b-a398-0cbc59a8e133"),
    }
    class Reply:
        def __init__(self,data,status=200,url="https://api.smartrecruiters.com/v1/companies/Wise/postings/744000145714264"):
            self.data=data;self.status_code=status;self.url=url
        def raise_for_status(self):
            if self.status_code>=400:raise RuntimeError("HTTP "+str(self.status_code))
        def json(self):return self.data
    @staticmethod
    def org():
        return {"name":"Wise","official_domain":"wise.jobs","allowed_domains":[],
                "seed_urls":["https://www.wise.jobs/"],"no_public_hint":False}
    @staticmethod
    def item(title):
        ident,uuid=WisePublicATSRegressionTests.IDS[title]
        return {"id":ident,"name":title,"uuid":uuid,"releasedDate":"2026-08-26T11:19:13.644Z",
                "location":{"city":"London"}}
    @staticmethod
    def candidate():
        title="Compliance Lead (Wise Platform)"
        ident,uuid=WisePublicATSRegressionTests.IDS[title]
        return {"title":title,"url":f"https://jobs.smartrecruiters.com/Wise/{ident}",
                "smartrecruiters_posting_id":ident,"posting_uuid":uuid,
                "smartrecruiters_detail_url":f"https://api.smartrecruiters.com/v1/companies/Wise/postings/{ident}"}
    @staticmethod
    def details(j,**updates):
        d={"id":j["smartrecruiters_posting_id"],"uuid":j["posting_uuid"],
           "name":j["title"],"postingUrl":j["url"]+"-compliance-lead-wise-platform-",
           "applyUrl":j["url"]+"-compliance-lead-wise-platform-?oga=true"}
        d.update(updates);return d
    @staticmethod
    def fetched(url,title=None,status=200):
        title=title or "Compliance Lead (Wise Platform)"
        return {"ok":status==200,"status":status,"final":url,"html":f"<title>{title} - Wise</title>",
                "text":title,"error":None}

    def test_complete_official_wise_inventory_finds_all_four_supplied_roles(self):
        posts=[self.item(t) for t in self.IDS]
        with patch("scanner.requests.get",return_value=self.Reply(
                {"totalFound":4,"content":posts})):
            inv=api_inventory(self.org())
        self.assertTrue(inv["complete"])
        self.assertEqual(inv["official_total"],4)
        self.assertEqual({j["title"] for j in inv["jobs"]},set(self.IDS))
        self.assertTrue(all(j["smartrecruiters_detail_url"].endswith("/"+j["smartrecruiters_posting_id"]) for j in inv["jobs"]))
        self.assertTrue(all(REL.search(j["title"]+" "+j["url"]) and SENIOR.search(j["title"]) for j in inv["jobs"]))

    def test_wise_official_api_and_matching_publication_allows_live_match(self):
        j=self.candidate();d=self.details(j)
        redirect_url=d["applyUrl"];form_url=("https://jobs.smartrecruiters.com/oneclick-ui/company/Wise/publication/"+
                                                j["posting_uuid"]+"?dcr_ci=Wise")
        with patch("scanner.requests.get",return_value=self.Reply(d)),patch(
            "scanner.fetch",side_effect=[
                self.fetched(j["url"]),self.fetched(redirect_url),self.fetched(form_url)]):
            result=validate_jobs([j],{job_key(j["url"])})[0]
        self.assertTrue(result["live"])
        self.assertTrue(result["board_present"])
        self.assertTrue(result["apply_live"])
        self.assertEqual(result["validation_reason"],"direct_live_and_current_board")

    def test_actual_wise_oga_redirect_to_matching_oneclick_is_valid(self):
        j=self.candidate();d=self.details(j)
        oneclick=("https://jobs.smartrecruiters.com/oneclick-ui/company/Wise/publication/"+
                  j["posting_uuid"]+"?dcr_ci=Wise")
        with patch("scanner.requests.get",return_value=self.Reply(d)),patch(
            "scanner.fetch",side_effect=[self.fetched(j["url"]),self.fetched(oneclick)]) as fetch:
            result=validate_jobs([j],{job_key(j["url"])})[0]
        self.assertTrue(result["apply_live"])
        self.assertEqual(result["apply_http_status"],200)
        self.assertEqual(fetch.call_count,2)

    def test_wise_wrong_oneclick_publication_redirect_fails(self):
        j=self.candidate();d=self.details(j)
        wrong="https://jobs.smartrecruiters.com/oneclick-ui/company/Wise/publication/00000000-0000-0000-0000-000000000000?dcr_ci=Wise"
        correct=("https://jobs.smartrecruiters.com/oneclick-ui/company/Wise/publication/"+
                  j["posting_uuid"]+"?dcr_ci=Wise")
        with patch("scanner.requests.get",return_value=self.Reply(d)),patch(
            "scanner.fetch",side_effect=[self.fetched(j["url"]),self.fetched(wrong),self.fetched(correct)]):
            result=validate_jobs([j],{job_key(j["url"])})[0]
        self.assertFalse(result["apply_live"])

    def test_missing_current_inventory_proof_rejects_linked_detail(self):
        j=self.candidate();d=self.details(j)
        with patch("scanner.requests.get",return_value=self.Reply(d)),patch("scanner.fetch") as fetch:
            result=validate_jobs([j],set())[0]
        self.assertFalse(result["apply_live"])
        self.assertEqual(result["validation_reason"],"not_on_current_board")
        fetch.assert_not_called()

    def test_wise_closed_or_changed_ats_identity_fails_closed(self):
        j=self.candidate()
        for changes in ({"uuid":"00000000-0000-0000-0000-000000000000"},
                        {"id":"0"},{"name":"Unrelated vacancy"},{"applyUrl":""},
                        {"postingUrl":"https://jobs.smartrecruiters.com/Other/123"}):
            with self.subTest(changes=changes),patch(
                "scanner.requests.get",return_value=self.Reply(self.details(j,**changes))),patch(
                "scanner.fetch") as fetch:
                result=validate_jobs([j],{job_key(j["url"])})[0]
            self.assertFalse(result["apply_live"])
            fetch.assert_not_called()

    def test_application_generic_redirect_or_wrong_role_fails_closed(self):
        j=self.candidate();d=self.details(j)
        form_url="https://jobs.smartrecruiters.com/oneclick-ui/company/Wise/publication/"+j["posting_uuid"]+"?dcr_ci=Wise"
        for form in (self.fetched("https://jobs.smartrecruiters.com/Wise"),
                     self.fetched(form_url,"Unrelated vacancy"),
                     self.fetched(form_url,status=404)):
            with self.subTest(form=form),patch("scanner.requests.get",return_value=self.Reply(d)),patch(
                "scanner.fetch",side_effect=[self.fetched(j["url"]),self.fetched(d["applyUrl"]),form]):
                result=validate_jobs([j],{job_key(j["url"])})[0]
            self.assertFalse(result["apply_live"])
            self.assertEqual(result["validation_reason"],"no_live_apply_control")



class WorkflowScheduleTests(unittest.TestCase):
    def test_vacancy_monitor_runs_twice_per_hour_without_dropping_cycles(self):
        with open(".github/workflows/vacancy-monitor.yml", encoding="utf-8") as handle:
            workflow = handle.read()
        self.assertIn('cron: "7,37 * * * *"', workflow)
        self.assertIn('timezone: "Europe/Amsterdam"', workflow)
        self.assertIn('group: vacancy-monitor-106-half-hourly', workflow)
        self.assertIn('cancel-in-progress: false', workflow)
        self.assertIn('queue: max', workflow)
        self.assertNotIn('cron: "30 5 * * 1-5"', workflow)

if __name__ == "__main__":
    unittest.main()
