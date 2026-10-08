"""Independent Breezy authority and pinned first-party route contract."""
import json
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))

class BreezyAuthorityContractTests(unittest.TestCase):
    def test_authority_and_manifest_mapping(self):
        authority = load("config/provider_authority.json")
        self.assertEqual(authority["schema_version"], 1)
        provider = authority["providers"]["breezy"]
        self.assertIn("first-party", provider["authority"])
        self.assertIn("uncorroborated zero", provider["zero_inventory"])
        mapping = load("config/provider_map.json")
        entries = [s for s in mapping["sources"]
                   if s["kind"] == "employer" and s["name"] == "Zerohash"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["platforms"]["breezy"]["status"], "PROVEN")
        manifest = load("config/sources.json")
        self.assertEqual(sum(s["kind"] == "employer" and s["name"] == "Zerohash"
                             for s in manifest["sources"]), 1)

    def test_feed_and_board_pinned_to_same_first_party_host(self):
        config = load("config/breezy_sources.json")
        self.assertEqual(config["provider"], "breezy")
        self.assertEqual(len(config["sources"]), 1)
        source = config["sources"][0]
        self.assertEqual(source["name"], "Zerohash")
        board = urlparse(source["board_url"])
        feed = urlparse(source["feed_url"])
        self.assertEqual((board.scheme, board.netloc), ("https", "zero-hash.breezy.hr"))
        self.assertEqual((feed.scheme, feed.netloc, feed.path),
                         ("https", board.netloc, "/json"))
        self.assertFalse(feed.query or feed.fragment)

if __name__ == "__main__":
    unittest.main()
