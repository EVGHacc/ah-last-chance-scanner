"""Post-inventory vacancy matching for v4.

Coverage/certification and matching are deliberately separate concerns.
"""
from dataclasses import dataclass
import re
from app.feedback import feedback_adjustment

DOMAIN_TERMS = {
    "aml": 3, "anti-money laundering": 3, "financial crime": 3, "fincrime": 3,
    "sanctions": 3, "compliance": 2, "regulatory": 2, "internal audit": 3,
    "governance": 2, "non-financial risk": 3, "risk assurance": 3,
    "controls": 2, "control": 1, "trust & safety": 2, "responsible ai": 2,
    "risk assessment": 2, "monitoring": 1, "testing": 1,
}
SENIOR_TERMS = {
    "chief": 4, "cco": 4, "cro": 4, "mlro": 4, "head": 4, "director": 4,
    "senior manager": 3, "lead": 2, "group lead": 3, "officer": 1,
}
LOCATION_TERMS = ("amsterdam", "netherlands", "london", "remote")
NEGATIVE_TERMS = ("intern", "internship", "graduate", "junior", "associate")


@dataclass(frozen=True)
class Match:
    employer: str
    job_id: str
    title: str
    location: str
    source_url: str
    score: int
    why: tuple[str, ...]
    limiters: tuple[str, ...]
    mismatch: tuple[str, ...]

    @property
    def strong(self) -> bool:
        return self.score >= 7


def _text(job):
    fields=("title","summary","short_summary","description","department","team","office","location")
    return " ".join(str(job.get(k) or "") for k in fields).casefold()


def score_job(employer: str, job: dict, source: str="", feedback_records: list[dict] | None=None) -> Match:
    text=_text(job); title=str(job.get("title") or ""); location=str(job.get("location") or job.get("office") or "")
    domain=[term for term in DOMAIN_TERMS if term in text]
    senior=[term for term in SENIOR_TERMS if term in text]
    negative=[term for term in NEGATIVE_TERMS if re.search(rf"\b{re.escape(term)}\b", title.casefold())]
    loc_ok=any(term in location.casefold() for term in LOCATION_TERMS)

    domain_score=min(5, max((DOMAIN_TERMS[t] for t in domain), default=0) + (1 if len(domain)>=2 else 0) + (1 if len(domain)>=4 else 0))
    senior_score=min(3, max((SENIOR_TERMS[t] for t in senior), default=0))
    location_score=2 if loc_ok else 0
    base=domain_score+senior_score+location_score-(4 if negative else 0)
    preference=feedback_adjustment(source,str(job.get("job_id") or ""),feedback_records or []) if source else 0
    score=max(1, min(10, base+preference))

    why=tuple(domain[:4]+senior[:2])
    limiters=() if loc_ok else ("location outside Amsterdam/Netherlands/London/fully remote preference",)
    mismatch=tuple(negative)
    url=str(job.get("apply_url") or job.get("job_url") or "")
    return Match(employer,str(job.get("job_id") or ""),title,location,url,score,why,limiters,mismatch)


def rank_inventory(employer: str, jobs: list[dict], minimum_score: int=7, source: str="", feedback_records: list[dict] | None=None) -> list[Match]:
    seen=set(); matches=[]
    for job in jobs:
        key=str(job.get("job_id") or job.get("apply_url") or job.get("job_url") or "")
        if not key or key in seen: continue
        seen.add(key)
        match=score_job(employer,job,source=source,feedback_records=feedback_records)
        if match.score>=minimum_score and match.source_url:
            matches.append(match)
    return sorted(matches,key=lambda m:(-m.score,m.employer.casefold(),m.title.casefold(),m.job_id))
