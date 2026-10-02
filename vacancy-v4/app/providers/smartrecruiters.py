from dataclasses import dataclass

class SmartRecruitersError(RuntimeError):
    pass

@dataclass(frozen=True)
class Job:
    job_id: str
    title: str
    summary: str
    job_url: str
    apply_url: str

def inventory(company, fetch_json, limit=100):
    offset=0; total=None; ids=[]
    while total is None or offset < total:
        payload=fetch_json('https://api.smartrecruiters.com/v1/companies/%s/postings?limit=%s&offset=%s' % (company,limit,offset))
        rows=payload.get('content') if isinstance(payload,dict) else None
        page_total=payload.get('totalFound') if isinstance(payload,dict) else None
        if not isinstance(rows,list) or not isinstance(page_total,int) or payload.get('offset') != offset:
            raise SmartRecruitersError('pagination schema changed')
        if total is None: total=page_total
        elif total != page_total: raise SmartRecruitersError('totalFound changed')
        if offset < total and not rows: raise SmartRecruitersError('pagination incomplete')
        for row in rows:
            ident=str(row.get('id') or row.get('uuid') or '').strip()
            if not ident or ident in ids: raise SmartRecruitersError('duplicate posting id')
            ids.append(ident)
        offset += len(rows)
    if len(ids) != (total or 0): raise SmartRecruitersError('count mismatch')
    jobs=[]
    for ident in ids:
        detail=fetch_json('https://api.smartrecruiters.com/v1/companies/%s/postings/%s' % (company,ident))
        title=str(detail.get('name') or '').strip(); job_url=detail.get('postingUrl'); apply_url=detail.get('applyUrl')
        sections=((detail.get('jobAd') or {}).get('sections') or {})
        summary=' '.join(str((sections.get(k) or {}).get('text') or '').strip() for k in ('jobDescription','qualifications','additionalInformation')).strip()[:360]
        if str((detail.get('company') or {}).get('identifier','')).casefold()!=company.casefold() or not title or not summary or not str(job_url).startswith('https://') or not str(apply_url).startswith('https://'):
            raise SmartRecruitersError('job invariant failed')
        jobs.append(Job(ident,title,summary,job_url,apply_url))
    return tuple(jobs), total or 0
