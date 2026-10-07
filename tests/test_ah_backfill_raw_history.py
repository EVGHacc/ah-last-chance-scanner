import json
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from scripts.backfill_raw_history import expected_raw_slots, validate_observation, verify_backfill, find_commit

class BackfillRawHistoryTests(unittest.TestCase):
    def sample(self, slot):
        return {
            "date":"2026-10-06","rawScheduledSlot":slot,"scheduledSlot":slot,
            "valid":True,"status":"OK","authMode":"user-refresh","categories":["Vlees"],
            "delaySeconds":0,"rawDelaySeconds":0,
            "stores":[{"storeId":s,"fetched":True} for s in (1463,1348,1135,4046,8728)]
        }

    def test_expected_slots_are_exactly_98_and_never_fabricate_start_gaps(self):
        slots=expected_raw_slots()
        self.assertEqual(98,len(slots))
        self.assertNotIn("17:30",slots)
        self.assertNotIn("17:33",slots)
        self.assertNotIn("17:36",slots)
        self.assertEqual(len(slots),len(set(slots)))

    def test_validation_rejects_wrong_slot_or_auth(self):
        o=self.sample("17:39")
        validate_observation(o,"2026-10-06","17:39")
        o["authMode"]="anonymous"
        with self.assertRaises(AssertionError):
            validate_observation(o,"2026-10-06","17:39")

    def test_find_commit_uses_exact_subject_filter_after_literal_grep(self):
        rows="aaa\tAH scan 2026-10-06 17:39\nbbb\tAH scan 2026-10-06 17:39 extra"
        with mock.patch("scripts.backfill_raw_history.git",return_value=rows):
            self.assertEqual("aaa",find_commit("2026-10-06","17:39"))

    def test_verify_requires_exact_files(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for slot in expected_raw_slots():
                (root/f"{slot.replace(':','')}.json").write_text(json.dumps(self.sample(slot)))
            report=verify_backfill(root,"2026-10-06")
            self.assertEqual(98,report["count"])
            (root/"1739.json").unlink()
            with self.assertRaises(AssertionError):
                verify_backfill(root,"2026-10-06")

if __name__=="__main__":
    unittest.main()
