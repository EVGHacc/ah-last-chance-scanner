from dataclasses import dataclass

class LeverError(RuntimeError):
    pass

@dataclass(frozen=True)
class LeverJob:
    id: str
    title: str
    hosted_url: str

def inventory(site, fetch_page, limit=100, max_pages=100):
    if not site or not 1 <= limit <= 100:
        raise ValueError('invalid Lever configuration')
    jobs={}; offset=0
    for _ in range(max_pages):
        payload=fetch_page(site, offset, limit)
        if not isinstance(payload,list):
            raise LeverError('structural change: expected JSON array')
        for raw in payload:
            if not isinstance(raw,dict):
                raise LeverError('structural change: posting is not an object')
            ident=raw.get('id'); title=raw.get('text'); hosted=raw.get('hostedUrl')
            if not all(isinstance(v,str) and v.strip() for v in (ident,title,hosted)):
                raise LeverError('structural change: required posting fields missing')
            if ident in jobs:
                raise LeverError('duplicate/page-wrap detected')
            jobs[ident]=LeverJob(ident,title,hosted)
        if len(payload) < limit:
            return tuple(jobs.values())
        offset += len(payload)
    raise LeverError('pagination cap reached before exhaustion')
