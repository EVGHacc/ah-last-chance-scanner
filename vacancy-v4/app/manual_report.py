"""Manual Vacancy v4 matching report from a verified provider snapshot.

This entry point defaults to read-only reporting. It never emails unless
--send is explicitly supplied together with a durable receipt ledger.
"""
import argparse
import json
import os
from pathlib import Path

from .matcher import rank_inventory
from .notify_runner import dispatch_new_matches


def collect_matches(snapshot: dict):
    if snapshot.get("failed") or not isinstance(snapshot.get("sources"), list):
        raise ValueError("Snapshot contains failed sources or missing inventory")
    matches = []
    for source in snapshot["sources"]:
        if source.get("coverage") != "verified_complete" or source.get("error"):
            raise ValueError("Refusing unverified source inventory")
        name = source.get("name")
        jobs = source.get("jobs")
        if not isinstance(name, str) or not isinstance(jobs, list):
            raise ValueError("Invalid inventory record")
        matches.extend((name, m) for m in rank_inventory(name, jobs, source=name))
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--receipt-ledger", type=Path)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    matches = collect_matches(snapshot)
    report = {
        "source_snapshot": str(args.snapshot),
        "matching_jobs": len(matches),
        "matches": [
            {"source": source, "job_id": m.job_id, "title": m.title,
             "employer": m.employer, "location": m.location,
             "score": m.score, "url": m.source_url}
            for source, m in matches
        ],
    }
    if args.send:
        if not args.receipt_ledger:
            raise SystemExit("Sending requires durable --receipt-ledger")
        if not os.environ.get("RESEND_API_KEY") or not os.environ.get("RESEND_CONTACT_EMAIL"):
            raise SystemExit("Sending requires RESEND_API_KEY and RESEND_CONTACT_EMAIL")
        # Caller must validate official live apply links before enabling sends.
        raise SystemExit("Live URL validation is not wired; fail closed without sending")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matching_jobs": len(matches), "report": str(args.output)}))


if __name__ == "__main__":
    main()
