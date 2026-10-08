"""Independent all-match report, preserving unknown statuses."""
from urllib.parse import urlparse


def build_report(raw, audit, *, feedback=None, receipts=None, live_checks=None):
    seen = {}
    for match in raw.get("matches", []):
        source, job_id = str(match["source"]), str(match["job_id"])
        key = source.casefold(), job_id
        url = str(match.get("url") or "")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("vacancy URL must use HTTPS")
        if key in seen:
            previous=seen[key]
            if (previous["url"] != url or previous["title"] != match["title"] or
                previous["employer"] != match["employer"] or previous["score"] != match["score"]):
                raise ValueError("conflicting data for duplicate job")
            continue
        fb = sorted([f for f in (feedback or []) if str(f.get("source","")).casefold() == key[0]
                     and str(f.get("job_id")) == job_id], key=lambda f:f.get("received_at",""))
        receipt = (receipts or {}).get(source + ":" + job_id)
        check = (live_checks or {}).get(source + ":" + job_id)
        score = match["score"]
        if not isinstance(score, (int,float)) or isinstance(score,bool):
            raise ValueError("numeric score required")
        seen[key] = {
            "source":source,"job_id":job_id,"employer":match["employer"],
            "title":match["title"],"location":match.get("location"),"score":score,
            "url":url,"scan_timestamp":raw.get("generated_at"),
            "match_status":"strong" if score>=7 else "other",
            "feedback_status":fb[-1].get("label","unknown") if fb else ("not_connected" if feedback is None else "no_feedback"),
            "feedback_history":fb,
            "notification_status":"event_accepted_delivery_unverified" if receipt else ("unknown" if receipts is None else "not_recorded"),
            "notification_receipt":receipt,
            "live_status":check.get("status","unknown") if check else "not_checked",
            "live_checked_at":check.get("checked_at") if check else None}
    return {"generated_at":raw.get("generated_at"),"provider_reports":raw.get("provider_reports"),
            "degraded":raw.get("degraded",True),"match_count":len(seen),
            "classification_audit":audit,"feedback_connected":feedback is not None,
            "receipts_connected":receipts is not None,
            "matches":sorted(seen.values(),key=lambda r:(-r["score"],r["employer"],r["title"]))}
