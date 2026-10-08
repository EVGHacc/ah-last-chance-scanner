import unittest
from app.gatekeeper_report import audit_classification
from app.gatekeeper_matches import build_report

def fixtures():
    manifest={"target_count":113,"sources":[{"kind":"employer","name":f"Employer {i}"} for i in range(113)]}
    provider_map={"sources":[{"kind":"employer","name":f"Employer {i}","platforms":{}} for i in range(113)]}
    provider_map["sources"][0]["platforms"]={"ashby":{"status":"PROVEN","evidence_url":"https://jobs.example.org/0","checked_at":"2026-10-08T10:00:00Z","route_type":"ats_api"}}
    ledger={"target_count":113,"certified_coverage":0,"records":[{"source_id":f"employer::Employer {i}","certification":"UNPROVEN"} for i in range(113)]}
    return manifest,provider_map,ledger

class GatekeeperReportTests(unittest.TestCase):
    def test_classification_requires_route_evidence(self):
        m,p,l=fixtures()
        result=audit_classification(m,p,l)
        self.assertEqual(result["evidence_complete"],1)
        self.assertEqual(len(result["unclassified"]),112)

    def test_exact_identity_set_required(self):
        m,p,l=fixtures()
        p["sources"][-1]["name"]="Unexpected"
        with self.assertRaises(ValueError):
            audit_classification(m,p,l)

    def test_report_retains_feedback_and_receipts(self):
        m,p,l=fixtures()
        raw={"matches":[{"source":"Employer 0","job_id":"123","employer":"Employer 0","title":"Head of Compliance","location":"Amsterdam","score":9,"url":"https://jobs.example.org/123"}]}
        fb=[{"source":"Employer 0","job_id":"123","label":"relevant","received_at":"2026-10-08T12:00:00Z","message_id":"msg-1"}]
        receipts={"Employer 0:123":{"event_id":"evt-1"}}
        report=build_report(raw,audit_classification(m,p,l),feedback=fb,receipts=receipts)
        self.assertEqual(report["match_count"],1)
        row=report["matches"][0]
        self.assertEqual(row["feedback_status"],"relevant")
        self.assertEqual(len(row["feedback_history"]),1)
        self.assertEqual(row["notification_status"],"event_accepted_delivery_unverified")
        self.assertEqual(row["live_status"],"not_checked")

if __name__=="__main__":
    unittest.main()
