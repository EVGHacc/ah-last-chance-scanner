"""Read-only enrichment of an existing v4 match artifact with persisted feedback."""
import argparse
import json
from pathlib import Path
from .gatekeeper_feedback import history_for_job


def enrich_snapshot(snapshot, feedback):
    rows = snapshot.get("matches")
    if not isinstance(rows, list) or not isinstance(feedback, list):
        raise ValueError("snapshot matches and feedback must be arrays")
    if not isinstance(snapshot.get("provenance"), dict):
        raise ValueError("snapshot provenance required")
    result = []
    identities = set()
    matched_feedback_ids = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("source") or not row.get("job_id"):
            raise ValueError("invalid match identity")
        key = (str(row["source"]).casefold(), str(row["job_id"]))
        if key in identities:
            raise ValueError("duplicate job identity in snapshot")
        identities.add(key)
        history = history_for_job(feedback, row["source"], row["job_id"])
        matched_feedback_ids.update(x.get("message_id") for x in history if x.get("message_id"))
        enriched = dict(row)
        enriched["feedback_history"] = history
        enriched["feedback_status"] = history[-1].get("label", "unknown") if history else "no_feedback"
        result.append(enriched)
    output = dict(snapshot)
    output["matches"] = result
    output["feedback_connection"] = "persisted_github_ledger"
    output["feedback_joined_messages"] = len(matched_feedback_ids)
    output["feedback_unmatched_messages"] = len({x.get("message_id") for x in feedback if isinstance(x, dict) and x.get("message_id")}) - len(matched_feedback_ids)
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    feedback = json.loads(args.feedback.read_text(encoding="utf-8"))
    report = enrich_snapshot(snapshot, feedback)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"matches": len(report["matches"]), "feedback_joined_messages": report["feedback_joined_messages"]}))


if __name__ == "__main__":
    main()
