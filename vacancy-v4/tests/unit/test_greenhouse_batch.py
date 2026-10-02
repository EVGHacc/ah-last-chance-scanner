import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from app.greenhouse_batch import run_batch


DOMAINS={"stripe":"stripe.com","ripple":"ripple.com"}


def payload(board,count=2):
    domain=DOMAINS[board]
    return {
        "jobs":[{
            "id":i,
            "title":f"Role {i}",
            "location":{"name":"Amsterdam"},
            "absolute_url":f"https://{domain}/jobs/{i}",
            "content":"<p>Own regulatory controls. Work with senior business leaders.</p>",
            "departments":[{"name":"Compliance"}],
            "offices":[{"name":"Amsterdam"}],
            "first_published":"2026-10-01T08:00:00Z",
            "updated_at":"2026-10-02T08:00:00Z",
        } for i in range(count)],
        "meta":{"total":count},
    }


class GreenhouseBatchDeveloperTests(unittest.TestCase):
    def test_all_current_greenhouse_targets_persist_complete_job_inventory(self):
        result=run_batch(lambda url:payload(url.split("/boards/")[1].split("/")[0],2))
        self.assertEqual(result["configured_sources"],2)
        self.assertEqual(result["verified_complete"],2)
        self.assertEqual(result["failed"],0)
        self.assertEqual({x["name"] for x in result["sources"]},{"Stripe","Ripple"})
        for row in result["sources"]:
            self.assertEqual(len(row["jobs"]),2)
            self.assertEqual(row["unique_jobs"],row["authoritative_total"])
            self.assertTrue(all(j["title"] and j["summary"] for j in row["jobs"]))


if __name__=="__main__": unittest.main()
