"""Read-only, evidence-conscious Vacancy v4 match overview. Never sends email."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


def identity(source, job_id):
    if not str(source).strip() or not str(job_id).strip():
        raise ValueError("missing vacancy identity")
    return str(source).removeprefix("employer::").removeprefix("recruiter::").casefold().strip(), str(job_id).strip()


def build_overview(snapshot, feedback, receipts=None):
    if not isinstance(snapshot.get("matches"), list):
        raise ValueError("missing matches")
    if not isinstance(feedback, list) or not isinstance(receipts or {}, dict):
        raise ValueError("invalid feedback or receipt ledger")
    generated_at = snapshot.get("generated_at")
    if not generated_at:
        raise ValueError("missing scan timestamp")
    history = {}
    for item in feedback:
        key = identity(item.get("source", ""), item.get("job_id", ""))
        history.setdefault(key, []).append({
            "label": item.get("label"), "received_at": item.get("received_at"),
            "message_id": item.get("message_id"),
        })
    for values in history.values():
        values.sort(key=lambda r: (r.get("received_at") or "", r.get("message_id") or ""))
    rows, seen = [], set()
    for match in snapshot["matches"]:
        key = identity(match.get("source", ""), match.get("job_id", ""))
        if key in seen:
            raise ValueError("duplicate match identity")
        seen.add(key)
        url = str(match.get("url") or "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("invalid vacancy link")
        score = match.get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 10:
            raise ValueError("invalid match score")
        entries = history.get(key, [])
        receipt = (receipts or {}).get(f"{match['source']}:{match['job_id']}", {})
        if not isinstance(receipt, dict):
            raise ValueError("invalid receipt")
        rows.append({
            "source": match["source"], "job_id": str(match["job_id"]),
            "employer": match.get("employer") or match["source"],
            "title": match.get("title") or "",
            "location": match.get("location") or "unknown",
            "score": score, "vacancy_url": url,
            "scan_timestamp": generated_at,
            "match_status": "strong" if score >= 7 else "other",
            "live_link_status": "not_checked",
            "notification_status": receipt.get("status", "unverified"),
            "provider_event_id": receipt.get("event_id"),
            "feedback": entries[-1]["label"] if entries else None,
            "feedback_history": entries,
        })
    if snapshot.get("unique_matches") != len(rows):
        raise ValueError("snapshot match count inconsistent")
    return {
        "generated_at": generated_at, "source_run_provider_reports": snapshot.get("provider_reports"),
        "degraded": bool(snapshot.get("degraded", True)),
        "coverage_status": "partial" if snapshot.get("degraded", True) else "provider_reports_complete_only",
        "unique_matches": len(rows), "matches": rows,
        "disclaimer": "Links and email delivery are not live-verified; provider report may omit failed scans.",
    }


def markdown_report(overview):
    lines = [
        "# Vacancy v4 — matchoverzicht",
        f"Snapshot: {overview['generated_at']}; matches: {overview['unique_matches']}; providerreports: {overview['source_run_provider_reports']}; dekking: {overview['coverage_status']}.",
        "Live-linkstatus en e-mailbezorging zijn niet bevestigd.",
        "",
        "| Werkgever | Functie | Locatie | Score | Bron | Scan | Match | Feedback | Historie | E-mail | Vacature |",
        "|---|---|---|---:|---|---|---|---|---:|---|---|",
    ]
    def safe(value):
        return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")
    for row in overview["matches"]:
        cols = [row["employer"], row["title"], row["location"], row["score"],
                row["source"], row["scan_timestamp"], row["match_status"],
                row["feedback"], len(row["feedback_history"]), row["notification_status"],
                f"[Link]({row['vacancy_url']})"]
        lines.append("| " + " | ".join(safe(x) for x in cols) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--receipts", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text())
    feedback = json.loads(args.feedback.read_text())
    receipts = json.loads(args.receipts.read_text()) if args.receipts and args.receipts.exists() else {}
    report = build_overview(snapshot, feedback, receipts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    args.output.with_suffix(".md").write_text(markdown_report(report))
    print(json.dumps({"matches": report["unique_matches"], "degraded": report["degraded"]}))


if __name__ == "__main__":
    main()
