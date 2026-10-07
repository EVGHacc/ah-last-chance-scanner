"""Bounded, feature-based preference feedback for Vacancy Scanner v4."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json, re
from pathlib import Path

LABEL_WEIGHTS={"relevant":1,"not_relevant":-2,"too_junior":-2,"wrong_location":-3,"too_technical":-1,"insufficient_experience":-2,"no_management_role":-2,"good_domain_fit":1,"good_seniority":1}
PHRASES=(("niet relevant","not_relevant"),("not relevant","not_relevant"),("te junior","too_junior"),("wrong location","wrong_location"),("verkeerde locatie","wrong_location"),("te technisch","too_technical"),("too technical","too_technical"),("onvoldoende ervaring","insufficient_experience"),("geen management rol","no_management_role"),("goede inhoudelijke fit","good_domain_fit"),("good fit","good_domain_fit"),("goede senioriteit","good_seniority"),("relevant","relevant"))

def canonical_source(value:str)->str:
    return re.sub(r"^(?:employer|recruiter)::","",(value or "").strip(),flags=re.I).casefold()

@dataclass(frozen=True)
class Feedback:
    source:str; job_id:str; label:str; received_at:str; message_id:str

def normalize_feedback(text:str)->str|None:
    clean=re.sub(r"\s+"," ",(text or "").casefold()).strip()
    for phrase,label in PHRASES:
        if phrase in clean:return label
    return None

def feedback_adjustment(source:str,job_id:str,records:list[dict])->int:
    src=canonical_source(source)
    vals=[LABEL_WEIGHTS.get(r.get("label"),0) for r in records if canonical_source(r.get("source",""))==src and str(r.get("job_id"))==str(job_id)]
    return max(-3,min(2,sum(vals)))

def feature_feedback_adjustment(features:dict,records:list[dict])->tuple[int,tuple[str,...]]:
    """Generalise explicit reason labels to comparable future jobs; bounded to [-3,+2]."""
    delta=0; reasons=[]
    labels=[r.get("label") for r in records]
    if features.get("technical") and "too_technical" in labels: delta-=1; reasons.append("feedback: technical roles")
    if features.get("junior") and "too_junior" in labels: delta-=2; reasons.append("feedback: junior roles")
    if features.get("outside_location") and "wrong_location" in labels: delta-=2; reasons.append("feedback: location")
    if not features.get("management") and "no_management_role" in labels: delta-=2; reasons.append("feedback: non-management roles")
    # insufficient_experience is intentionally domain-specific: only learn from persisted feature snapshots.
    disliked=set()
    liked=set()
    for r in records:
        fs=r.get("features") or {}
        domains=set(fs.get("domains") or [])
        if r.get("label") in {"insufficient_experience","not_relevant"}: disliked|=domains
        if r.get("label") in {"relevant","good_domain_fit"}: liked|=domains
    overlap=set(features.get("domains") or []) & (disliked-liked)
    if overlap: delta-=1; reasons.append("feedback: domain experience")
    return max(-3,min(2,delta)),tuple(reasons)

def append_feedback(path:Path,feedback:Feedback)->bool:
    path.parent.mkdir(parents=True,exist_ok=True); rows=json.loads(path.read_text()) if path.exists() else []
    if any(r.get("message_id")==feedback.message_id for r in rows):return False
    rows.append(asdict(feedback)); path.write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n"); return True

def make_feedback(source,job_id,label,message_id):
    if label not in LABEL_WEIGHTS:raise ValueError("unsupported feedback label")
    return Feedback(source,str(job_id),label,datetime.now(timezone.utc).isoformat(),message_id)
