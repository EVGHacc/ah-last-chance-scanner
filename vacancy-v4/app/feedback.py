"""Bounded preference feedback for Vacancy Scanner v4.

Inbound email is untrusted. Only normalized labels are persisted/applied.
Hard certification, URL and location gates are deliberately out of scope.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import re
from pathlib import Path

LABEL_WEIGHTS = {
    "relevant": 1,
    "not_relevant": -2,
    "too_junior": -2,
    "wrong_location": -3,
    "too_technical": -1,
    "insufficient_experience": -2,
    "no_management_role": -2,
    "good_domain_fit": 1,
    "good_seniority": 1,
}
PHRASES = (
    ("niet relevant", "not_relevant"), ("not relevant", "not_relevant"),
    ("te junior", "too_junior"), ("wrong location", "wrong_location"),
    ("verkeerde locatie", "wrong_location"), ("te technisch", "too_technical"),
    ("too technical", "too_technical"), ("onvoldoende ervaring", "insufficient_experience"),
    ("geen management rol", "no_management_role"), ("goede inhoudelijke fit", "good_domain_fit"),
    ("good fit", "good_domain_fit"), ("goede senioriteit", "good_seniority"),
    ("relevant", "relevant"),
)

@dataclass(frozen=True)
class Feedback:
    source: str
    job_id: str
    label: str
    received_at: str
    message_id: str

def normalize_feedback(text: str) -> str | None:
    clean=re.sub(r"\s+"," ",(text or "").casefold()).strip()
    for phrase,label in PHRASES:
        if phrase in clean:
            return label
    return None

def feedback_adjustment(source: str, job_id: str, records: list[dict]) -> int:
    vals=[LABEL_WEIGHTS.get(r.get("label"),0) for r in records
          if r.get("source")==source and str(r.get("job_id"))==str(job_id)]
    return max(-3,min(2,sum(vals)))

def append_feedback(path: Path, feedback: Feedback) -> bool:
    path.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    if path.exists():
        rows=json.loads(path.read_text())
    if any(r.get("message_id")==feedback.message_id for r in rows):
        return False
    rows.append(asdict(feedback))
    path.write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    return True

def make_feedback(source, job_id, label, message_id):
    if label not in LABEL_WEIGHTS: raise ValueError("unsupported feedback label")
    return Feedback(source,str(job_id),label,datetime.now(timezone.utc).isoformat(),message_id)
