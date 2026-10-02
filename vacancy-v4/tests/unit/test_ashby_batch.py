import json
import sys
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.ashby_batch import load_config, run_batch


def ident(i):
    return f"00000000-0000-4000-8000-{i:012d}"

def payload(board, count=2):
    return {"apiVersion":"1","jobs":[
        {"title":f"Role {i}",
         "jobUrl":f"https://jobs.ashbyhq.com/{board}/{ident(i)}",
         "applyUrl":f"https://jobs.ashbyhq.com/{board}/{ident(i)}/application",
         "isListed":True,"location":"Amsterdam","department":"Risk","team":"Compliance",
         "descriptionPlain":f"Lead risk and compliance work for role {i}. Partner with senior stakeholders."}
        for i in range(count)
    ]}

def html_for(url, count=1, extra_mollie=False):
    if "jobs.mollie.com/vacancies/" in url:
        job_id=url.rstrip("/").split("/")[-1]
        return f'''<html><head><script type="application/ld+json">{{
          "@context":"https://schema.org","@type":"JobPosting",
          "title":"First-party reconciled role",
          "description":"Lead a control programme. Work with senior leaders.",
          "jobLocation":{{"@type":"Place","address":{{"addressLocality":"Amsterdam","addressCountry":"NL"}}}}
        }}</script></head><body>
        <a href="https://jobs.ashbyhq.com/mollie/{job_id}">job</a>
        <a href="https://jobs.ashbyhq.com/mollie/{job_id}/application">Apply now</a>
        </body></html>'''
    if "mollie" in url:
        n=count+(1 if extra_mollie else 0)
        return "\n".join(f'/vacancies/{ident(i)}' for i in range(n))
    return "<html></html>"


class AshbyBatchDeveloperTests(unittest.TestCase):
    def test_configured_sources_are_real_v4_targets_and_persist_jobs(self):
        result=run_batch(
            lambda url: payload(url.rsplit("/",1)[-1],1),
            lambda url: html_for(url,1),
        )
        self.assertEqual(result["schema_version"],2)
        self.assertEqual(result["configured_sources"],4)
        self.assertEqual(result["verified_complete"],4)
        self.assertEqual(result["failed"],0)
        for row in result["sources"]:
            self.assertEqual(len(row["jobs"]),row["unique_jobs"])
            self.assertTrue(all(j["title"] and j["summary"] for j in row["jobs"]))

    def test_first_party_only_live_job_is_reconciled_and_described(self):
        result=run_batch(
            lambda url: payload(url.rsplit("/",1)[-1],1),
            lambda url: html_for(url,1,extra_mollie=True),
        )
        row=next(x for x in result["sources"] if x["name"]=="Mollie")
        self.assertEqual(row["coverage"],"verified_complete")
        self.assertEqual(row["provider_unique_jobs"],1)
        self.assertEqual(row["first_party_unique_jobs"],2)
        self.assertEqual(row["unique_jobs"],2)
        self.assertEqual(row["reconciled_first_party_only_ids"],[ident(1)])
        first_party=next(j for j in row["jobs"] if j["job_id"]==ident(1))
        self.assertEqual(first_party["title"],"First-party reconciled role")
        self.assertIn("Lead a control programme.",first_party["summary"])
        self.assertIn("Amsterdam",first_party["location"])
        self.assertEqual(first_party["record_source"],"first_party_reconciled")
        self.assertEqual(row["evidence_kind"],"official_complete_payload_plus_first_party_reconciled")

    def test_hash_is_stable_for_complete_inventory(self):
        first=run_batch(lambda url: payload(url.rsplit("/",1)[-1],2),lambda url: html_for(url,2))
        second=run_batch(lambda url: payload(url.rsplit("/",1)[-1],2),lambda url: html_for(url,2))
        self.assertEqual(
            [x["jobs_sha256"] for x in first["sources"]],
            [x["jobs_sha256"] for x in second["sources"]],
        )

    def test_duplicate_config_source_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"c.json"
            p.write_text(json.dumps({"schema_version":1,"provider":"ashby","sources":[
                {"name":"OpenAI","board":"openai","first_party_evidence_url":"https://openai.com/careers/search/"},
                {"name":"OpenAI","board":"openai","first_party_evidence_url":"https://openai.com/careers/search/"}
            ]}))
            with self.assertRaises(ValueError): load_config(p)


if __name__=="__main__": unittest.main()
