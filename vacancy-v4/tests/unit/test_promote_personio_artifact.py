import json
import unittest
from app.promote_personio_artifact import validate_pair

class PersonioPromotionContractTests(unittest.TestCase):
    def setUp(self):
        job = dict(job_id="1", title="Risk Lead", short_summary="Full description",
                   job_url="https://coinmerce.jobs.personio.com/job/1",
                   apply_url="https://coinmerce.jobs.personio.com/job/1/apply")
        source = dict(name="Coinmerce", coverage="verified_complete", unique_jobs=1,
                      checked_at="2026-10-07T22:10:38+00:00", error=None, jobs=[job])
        self.first = dict(provider="personio", configured_sources=1,
                          verified_complete=1, failed=0, sources=[source])
        self.second = json.loads(json.dumps(self.first))
        self.second["sources"][0]["checked_at"] = "2026-10-07T22:10:44+00:00"
        self.manifest = dict(sources=[dict(kind="employer", name="Coinmerce")])
        self.mapping = dict(sources=[dict(kind="employer", name="Coinmerce",
                              platforms=dict(personio=dict(status="PROVEN")))])
        self.config = dict(provider="personio", sources=[dict(name="Coinmerce")])
        self.authority = dict(providers=dict(personio=dict(authority="XML feed")))

    def check(self):
        return validate_pair(self.first, self.second, self.manifest,
                             self.mapping, self.config, self.authority)

    def test_accepts_consecutive_green_proofs(self):
        one, two = self.check()
        self.assertEqual(one["unique_jobs"], two["unique_jobs"])

    def test_rejects_zero(self):
        self.first["sources"][0]["unique_jobs"] = 0
        with self.assertRaises(ValueError):
            self.check()

    def test_rejects_changed_apply_route(self):
        self.second["sources"][0]["jobs"][0]["apply_url"] += "/changed"
        with self.assertRaises(ValueError):
            self.check()

    def test_rejects_unproven_mapping(self):
        self.mapping["sources"][0]["platforms"]["personio"]["status"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            self.check()

if __name__ == "__main__":
    unittest.main()
