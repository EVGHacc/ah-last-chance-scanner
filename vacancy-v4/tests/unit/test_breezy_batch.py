import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.breezy_batch import run_batch


class BreezyBatchTests(unittest.TestCase):
    def test_valid_and_invalid_feed_isolated(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "breezy.json"
            config.write_text(json.dumps({"schema_version": 1, "provider": "breezy",
                "sources": [{"name": "Zerohash", "board_url": "https://zero-hash.breezy.hr",
                             "feed_url": "https://zero-hash.breezy.hr/json"}]}))
            job = {"job_id": "3ccb0da6cb42", "title": "Risk Lead",
                   "short_summary": "Risk governance leadership",
                   "job_url": "https://zero-hash.breezy.hr/p/3ccb0da6cb42-risk-lead",
                   "apply_url": "https://zero-hash.breezy.hr/p/3ccb0da6cb42-risk-lead/apply"}
            with patch("app.breezy_batch.load_sources", return_value=[SimpleNamespace(name="Zerohash")]), \
                 patch("app.breezy_batch.parse_inventory", return_value=[job]):
                result = run_batch(fetcher=lambda _: [], config_path=config)
            self.assertEqual((result["verified_complete"], result["failed"]), (1, 0))
            with patch("app.breezy_batch.load_sources", return_value=[SimpleNamespace(name="Zerohash")]), \
                 patch("app.breezy_batch.parse_inventory", side_effect=ValueError("zero")):
                result = run_batch(fetcher=lambda _: [], config_path=config)
            self.assertEqual((result["verified_complete"], result["failed"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
