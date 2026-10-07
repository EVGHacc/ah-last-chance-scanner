import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.providers.personio import PersonioError, parse_inventory

BOARD = "https://coinmerce.jobs.personio.com"
FEED = '''<workzag-jobs>
  <position><id>1001</id><name>Risk Director</name><office>Amsterdam</office>
    <jobDescriptions><jobDescription><value><![CDATA[<p>Lead compliance risk governance for regulated entities.</p>]]></value></jobDescription></jobDescriptions>
  </position>
  <position><id>1002</id><name>Compliance Lead</name><office>Schiphol-Rijk</office>
    <jobDescriptions></jobDescriptions>
  </position>
</workzag-jobs>'''


def detail(url):
    ident = url.split("/")[-1]
    title = "Risk Director" if ident == "1001" else "Compliance Lead"
    return f'<html><h1>{title}</h1><p>Develop and manage a strong financial crime compliance framework.</p><a href="/job/{ident}/apply">Apply</a></html>'


class PersonioTests(unittest.TestCase):
    def test_full_feed_and_live_apply(self):
        jobs = parse_inventory(FEED, BOARD, detail)
        self.assertEqual([x["job_id"] for x in jobs], ["1001", "1002"])
        self.assertEqual(jobs[0]["location"], "Amsterdam")
        self.assertTrue(all(x["apply_url"].endswith("/apply") for x in jobs))
        self.assertIn("financial crime", jobs[1]["short_summary"])

    def test_empty_inventory_is_not_a_proof(self):
        with self.assertRaises(PersonioError):
            parse_inventory("<workzag-jobs/>", BOARD, detail)

    def test_duplicate_id_rejected(self):
        with self.assertRaises(PersonioError):
            parse_inventory(FEED.replace("<id>1002</id>", "<id>1001</id>"), BOARD, detail)

    def test_cross_board_apply_rejected(self):
        def bad(url):
            return detail(url).replace("/job/1001/apply", "https://evil.example/job/1001/apply")
        with self.assertRaises(PersonioError):
            parse_inventory(FEED, BOARD, bad)

    def test_wrong_detail_title_rejected(self):
        with self.assertRaises(PersonioError):
            parse_inventory(FEED, BOARD, lambda url: detail(url).replace("Risk Director", "Other Role"))

    def test_xml_entities_rejected(self):
        with self.assertRaises(PersonioError):
            parse_inventory('<!DOCTYPE x [<!ENTITY x "abc">]><workzag-jobs/>', BOARD, detail)


if __name__ == "__main__":
    unittest.main()
