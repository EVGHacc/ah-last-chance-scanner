import unittest
from app.providers.breezy import BreezyError, parse_inventory

BOARD = "https://zero-hash.breezy.hr"
ID = "3ccb0da6cb42"
URL = f"{BOARD}/p/{ID}-operational-risk-manager"
PAYLOAD = [{"_id": ID, "name": "Operational Risk Manager", "url": URL,
            "location": {"name": "Amsterdam"}, "department": "Risk"}]
DETAIL = f'''<html><head><title>Operational Risk Manager at zerohash</title></head>
<body><p>Own the operational risk framework and report to the board on RCSA.</p>
<a href="/p/{ID}-operational-risk-manager/apply">Apply</a></body></html>'''


class BreezyDeveloperTests(unittest.TestCase):
    def test_first_party_inventory_and_apply(self):
        jobs = parse_inventory(PAYLOAD, BOARD, lambda _: DETAIL)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], ID)
        self.assertEqual(jobs[0]["location"], "Amsterdam")
        self.assertEqual(jobs[0]["apply_url"], URL + "/apply")

    def test_uncorroborated_zero_fails_closed(self):
        with self.assertRaises(BreezyError):
            parse_inventory([], BOARD, lambda _: DETAIL)

    def test_duplicate_ids_fail_closed(self):
        with self.assertRaises(BreezyError):
            parse_inventory(PAYLOAD + PAYLOAD, BOARD, lambda _: DETAIL)

    def test_cross_board_job_fails_closed(self):
        wrong = [dict(PAYLOAD[0], url=URL.replace("zero-hash", "other"))]
        with self.assertRaises(BreezyError):
            parse_inventory(wrong, BOARD, lambda _: DETAIL)

    def test_missing_apply_fails_closed(self):
        with self.assertRaises(BreezyError):
            parse_inventory(PAYLOAD, BOARD, lambda _: DETAIL.replace("/apply", "/gone"))

    def test_wrong_detail_title_fails_closed(self):
        with self.assertRaises(BreezyError):
            parse_inventory(PAYLOAD, BOARD, lambda _: DETAIL.replace("Operational Risk Manager", "Other Job"))

    def test_short_detail_fails_closed(self):
        with self.assertRaises(BreezyError):
            parse_inventory(PAYLOAD, BOARD, lambda _: DETAIL.replace("Own the operational risk framework and report to the board on RCSA.", "Short"))

    def test_malformed_feed_fails_closed(self):
        with self.assertRaises(BreezyError):
            parse_inventory({"jobs": PAYLOAD}, BOARD, lambda _: DETAIL)


if __name__ == "__main__":
    unittest.main()
