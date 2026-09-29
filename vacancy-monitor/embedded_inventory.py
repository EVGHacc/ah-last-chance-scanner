"""First-party embedded vacancy catalogues for the N26 and Revolut careers sites.

These are official page payloads, not external search/cache hits. An index may
yield candidates while remaining PARTIAL if its full advertised count is not met.
"""
import json
import re
import unicodedata
from urllib.parse import urlparse
from bs4 import BeautifulSoup

_UUID = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$",re.I)
_N26_SEQUENCE = re.compile(r'"((?:\\.|[^"\\]){4,180})",(?:"id",)?(\d{7,9})(?=,|])')
_ROUTER_CHUNK = re.compile(r'__reactRouterContext\.streamController\.enqueue\(("(?:\\.|[^"\\])*")\)')


def _slug(title):
    raw=unicodedata.normalize("NFKD",title)
    ascii_only="".join(c for c in raw if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+","-",ascii_only).strip("-")


def _advertised_total(text,kind):
    if kind=="N26":
        pattern=r"\bsearch from\s+([\d,]+)\s+positions\b"
    else:
        pattern=r"\b(?:we have|search from)\s+([\d,]+)\s+open positions\b"
    found=re.search(pattern,text,re.I)
    return int(found.group(1).replace(",","")) if found else None


def embedded_inventory(name,html,source):
    """Return official current job candidates and proof, never extrapolate a total."""
    path=urlparse(source).path.rstrip("/")
    host=urlparse(source).netloc.lower()
    if name=="N26":
        if not host.endswith("n26.com") or path!="/en-eu/careers":return None
    elif name=="Revolut":
        if not host.endswith("revolut.com") or path!="/careers":return None
    else:return None
    soup=BeautifulSoup(html,"html.parser")
    total=_advertised_total(soup.get_text(" ",strip=True),name)
    jobs={}
    error=None
    if name=="N26":
        chunks=[]
        for script in soup.find_all("script"):
            content=script.string or script.get_text() or ""
            for match in _ROUTER_CHUNK.finditer(content):
                try:chunks.append(json.loads(match.group(1)))
                except (ValueError,TypeError):pass
        decoded="".join(chunks)
        for title_raw,ident in _N26_SEQUENCE.findall(decoded):
            try:title=json.loads('"'+title_raw+'"')
            except ValueError:continue
            if not isinstance(title,str) or len(title.strip())<4:continue
            url="https://n26.com/en-eu/careers/positions/"+ident
            jobs[ident]={"title":title.strip(),"url":url,"source_job_id":ident,
                         "embedded_job_id":ident,"embedded_provider":"N26",
                         "location":"","team":"","department":""}
        if not chunks:error="n26_react_router_data_missing"
    else:
        script=soup.find("script",id="__NEXT_DATA__")
        data={}
        if script:
            try:data=json.loads(script.string or script.get_text())
            except (ValueError,TypeError):data={}
        raw=data.get("props",{}).get("pageProps",{}).get("positions")
        if not isinstance(raw,list):
            raw=[];error="revolut_positions_index_missing"
        for posting in raw:
            if not isinstance(posting,dict):continue
            ident=posting.get("id")
            title=posting.get("text")
            if not isinstance(ident,str) or not _UUID.fullmatch(ident):continue
            if not isinstance(title,str) or len(title.strip())<4:continue
            ident=ident.lower()
            title=title.strip()
            url="https://www.revolut.com/careers/position/"+_slug(title)+"-"+ident+"/"
            locations=posting.get("locations") or []
            location="; ".join(x.get("name","") for x in locations if isinstance(x,dict))
            team=posting.get("team") if isinstance(posting.get("team"),str) else ""
            jobs[ident]={"title":title,"url":url,"source_job_id":ident,
                         "embedded_job_id":ident,"embedded_provider":"Revolut",
                         "location":location,"department":team,"team":team}
        if len(jobs)!=len(raw):error="revolut_index_malformed_or_duplicate"
    complete=bool(total is not None and len(jobs)==total and not error)
    if not complete and not error:error=f"incomplete_catalogue_{len(jobs)}_of_{total}"
    return {"source":source,"jobs":list(jobs.values()),"official_total":total,
            "pages":1,"terminal":True,"complete":complete,
            "evidence_kind":"first_party_embedded_index","error":error}
