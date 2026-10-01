#!/usr/bin/env python3
import csv, json, os, re, time, concurrent.futures, unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus, parse_qs, unquote, urlencode, urlunparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from embedded_inventory import embedded_inventory

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; DATA.mkdir(exist_ok=True)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36 VacancyMonitor/1.0"
H={"User-Agent":UA,"Accept-Language":"en-GB,en;q=0.9,nl;q=0.8"}
TIMEOUT=int(os.getenv("VACANCY_TIMEOUT","12")); WORKERS=int(os.getenv("VACANCY_WORKERS","12"))
BROWSER_BUDGET=int(os.getenv("VACANCY_BROWSER_BUDGET","660"))
BROWSER_ORG_BUDGET=int(os.getenv("VACANCY_BROWSER_ORG_BUDGET","85"))
BROWSER_URL_BUDGET=int(os.getenv("VACANCY_BROWSER_URL_BUDGET","28"))
ATS=("myworkdayjobs.com","workday.com","oraclecloud.com","greenhouse.io","lever.co","teamtailor.com","recruitee.com","ashbyhq.com","breezy.hr","smartrecruiters.com","successfactors.com","eightfold.ai","icims.com")
CAREER=re.compile(r"(job|career|vacanc|position|opportunit|werken.?bij|open.?roles)",re.I)
REL=re.compile(r"(compliance|risk|audit|anti.?money|aml|financial.?crime|sanction|governance|regulat|controls?|assurance|oversight|mlro|cco|cro|responsible.?ai|trust.?safety|resilien|continuity|business.?control|integrity|fraud|investigation|financial.?intelligence|conduct|ethics|remediation|non.?financial|financieel.?economische.?criminaliteit|witwassen)",re.I)
JOBURL=re.compile(r"(/overview/[0-9]+(?:/|$)|/job(?:s)?/|/vacanc|/position|/career|/opportunit|job[_-]|vacature|search-jobs|/offre-de-emploi/|/stellenangebot/)",re.I)
AUDIT_REL=re.compile(r"(compliance|risk|audit|anti.?money|aml|financial.?crime|sanction|governance|regulat|control|assurance|oversight|resilien|continuity|integrity|fraud|investigation|financial.?intelligence|conduct|ethics|responsible.?ai|trust.?safety|remediation|non.?financial)",re.I)
AUDIT_SENIOR=re.compile(r"(head|director|senior|lead|chief|vice.?president|\\bvp\\b|principal|partner|manager|expert|global|regional|\\bmlro\\b|\\bcco\\b|\\bcro\\b)",re.I)
SENIOR=re.compile(r"(head|director|executive.?director|senior|lead|chief|vice.?president|vp|principal|partner|manager|hoofd|directeur|global|regional|strateg|expert|business.?resilien.?officer|operational.?continuity)",re.I)
APPLY=re.compile(r"(apply.?now|\bapply\b|solliciteer|submit.?application|start.?application)",re.I)
PAGING=re.compile(r"(next|volgende|suivant|weiter|load more|toon meer|show more|page [2-9])",re.I)
DYNAMIC_MORE=re.compile(r"(load more|toon meer|show more|view more|see more|meer vacatures|more jobs)",re.I)
LISTING_URL=re.compile(r"(/jobs?/?$|/vacatures/?$|job-search|search-jobs|search-results|/positions/?$|open-roles|open-jobs|careers/search|offre-de-emploi/liste)",re.I)
CLOSED=re.compile(r"(no.?longer.?available|(?:position|job|vacancy).{0,65}(?:has.?been.?filled|is.?filled|is.?closed|was.?filled)|job you are trying to apply for has been filled|vacature.?is.?gesloten|applications?.?closed|expired)",re.I)
COMMON=("/careers","/jobs","/vacatures","/job-search","/open-roles","/positions")
API_BOARDS={
    "Morgan Stanley":{"type":"workday","url":"https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/External/jobs","board":"https://ms.wd5.myworkdayjobs.com/External"},
    "Deutsche Bank":{"type":"workday","url":"https://db.wd3.myworkdayjobs.com/wday/cxs/db/DBWebsite/jobs","board":"https://db.wd3.myworkdayjobs.com/DBWebsite"},
    "PayPal":{"type":"workday","url":"https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs","board":"https://paypal.wd1.myworkdayjobs.com/jobs"},
    "Mastercard":{"type":"workday","url":"https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs","board":"https://mastercard.wd1.myworkdayjobs.com/CorporateCareers"},
    "State Street":{"type":"workday","url":"https://statestreet.wd1.myworkdayjobs.com/wday/cxs/statestreet/Global/jobs","board":"https://statestreet.wd1.myworkdayjobs.com/Global"},
    "Lloyds Banking Group":{"type":"workday","url":"https://lbg.wd3.myworkdayjobs.com/wday/cxs/lbg/LBG_Careers/jobs","board":"https://lbg.wd3.myworkdayjobs.com/LBG_Careers"},
    "Visa":{"type":"workday","url":"https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs","board":"https://visa.wd5.myworkdayjobs.com/Visa"},
    "Zerohash":{"type":"breezy","url":"https://zero-hash.breezy.hr/json","board":"https://zero-hash.breezy.hr"},
    # Public inventory endpoints linked from each organisation's official careers page.
    "Tide":{"type":"greenhouse","url":"https://boards-api.greenhouse.io/v1/boards/tide/jobs","board":"https://job-boards.greenhouse.io/tide"},
    "Surepay":{"type":"greenhouse","url":"https://boards-api.eu.greenhouse.io/v1/boards/surepay/jobs","board":"https://job-boards.eu.greenhouse.io/surepay"},
    "Finom":{"type":"lever","url":"https://api.eu.lever.co/v0/postings/pnlfin","board":"https://jobs.eu.lever.co/pnlfin"},
    "Varrlyn":{"type":"smartrecruiters","url":"https://api.smartrecruiters.com/v1/companies/Varrlyn/postings","board":"https://jobs.smartrecruiters.com/Varrlyn"},
    # wise.jobs/Workflow redirects to this exact Wise publisher/application system.
    "Wise":{"type":"smartrecruiters","url":"https://api.smartrecruiters.com/v1/companies/Wise/postings","board":"https://jobs.smartrecruiters.com/Wise"},
    "Airwallex":{"type":"ashby","url":"https://api.ashbyhq.com/posting-api/job-board/airwallex","board":"https://jobs.ashbyhq.com/airwallex"},
    "IBANfirst":{"type":"recruitee","url":"https://careers.ibanfirst.com/api/offers/","board":"https://careers.ibanfirst.com"}
}
STATIC_BOARDS={
    "Lime Search":{"url":"https://www.limesearch.nl/open-finance-posities","href":r"/positie/"},
    "Vroom":{"url":"https://vroomsearch.com/nl/vacatures","href":r"/nl/vacature/"},
    "Lloyds Banking Group":{"url":"https://www.lloydsbankinggroup.com/site-map.html/1000","href":r"/careers/job-search/workday-job\\.[0-9]+\\.html"}
}

def iso(): return datetime.now(timezone.utc).isoformat()
def nldate(): return datetime.now(ZoneInfo("Europe/Amsterdam")).date().isoformat()
def hostname(u): return (urlparse(u).hostname or "").lower().removeprefix("www.")
def origin(u):
    p=urlparse(u); return f"{p.scheme or 'https'}://{p.netloc}"
def isats(u):
    h=hostname(u); return any(h==a or h.endswith("."+a) for a in ATS)
def allowed(u,o):
    h=hostname(u); ds=[o["official_domain"]]+o["allowed_domains"]
    return any(h==d or h.endswith("."+d) for d in ds) or isats(u)
def norm(u):
    p=urlparse(u)
    if "duckduckgo.com" in (p.hostname or "") and p.path.startswith("/l/"):
        q=parse_qs(p.query)
        if q.get("uddg"): return unquote(q["uddg"][0]).split("#")[0]
    return u.split("#")[0]

def job_key(u):
    """Stable comparison key for the same vacancy URL across redirects/tracking params."""
    p=urlparse(norm(u))
    pairs=[]
    for k,vals in parse_qs(p.query,keep_blank_values=True).items():
        if k.lower().startswith("utm_") or k.lower() in ("gclid","fbclid","mc_cid","mc_eid"):
            continue
        for v in vals: pairs.append((k,v))
    query=urlencode(sorted(pairs),doseq=True)
    path=(p.path.rstrip("/") or "/")
    return urlunparse(((p.scheme or "https").lower(),(p.netloc or "").lower(),path,"",query,""))

def load_registry():
    out=[]
    with open(ROOT/"registry.tsv",encoding="utf-8") as f:
        for r in csv.DictReader(f,delimiter="\t"):
            r["seed_urls"]=[x for x in (r.get("seed_urls") or "").split(";") if x]
            r["allowed_domains"]=[x for x in (r.get("allowed_domains") or "").split(";") if x]
            r["no_public_hint"]=r["no_public_hint"]=="1"; out.append(r)
    if len(out)!=106: raise RuntimeError(f"registry count {len(out)} != 106")
    return out

def fetch(u,method="http"):
    t=time.monotonic()
    try:
        r=requests.get(u,headers=H,timeout=TIMEOUT,allow_redirects=True)
        body=r.text or ""; ok=r.status_code==200 and len(body)>300
        txt=BeautifulSoup(body,"html.parser").get_text(" ",strip=True) if "<" in body[:500] else body
        return {"ok":ok,"url":u,"final":r.url,"status":r.status_code,"html":body[:1200000],"text":txt[:200000],"method":method,"error":None if ok else f"HTTP {r.status_code}","ms":int((time.monotonic()-t)*1000)}
    except Exception as e:
        return {"ok":False,"url":u,"final":u,"status":None,"html":"","text":"","method":method,"error":f"{type(e).__name__}: {e}","ms":int((time.monotonic()-t)*1000)}

AIRWALLEX_JOB_ID=re.compile(r"/(?:job/|airwallex/)([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})(?:/|$)",re.I)

def airwallex_id(url):
    m=AIRWALLEX_JOB_ID.search(urlparse(url).path)
    return m.group(1).lower() if m else None

def airwallex_official_url(posting):
    identifier=airwallex_id(posting.get("jobUrl",""))
    if not identifier or str(posting.get("id") or "").lower()!=identifier:return None
    raw=unicodedata.normalize("NFKD",posting.get("title",""))
    slug=re.sub(r"[^a-z0-9]+","-","".join(c for c in raw if not unicodedata.combining(c)).lower()).strip("-")
    return "https://careers.airwallex.com/job/"+identifier+"/"+slug+"/" if slug else None

def strategic_inventory_match(job):
    """Discover strategic roles using title and department/team; no employer boilerplate."""
    title=job.get("title","")
    context=" ".join(str(job.get(k) or "") for k in ("department","team"))
    return bool(SENIOR.search(title) and (REL.search(title) or REL.search(context)))

def discover_official_ats(pages,o):
    """Derive public provider feeds only from a first-party careers page or authoritative seed."""
    configs=[]; seen=set()
    primary=[o["official_domain"]]+o["allowed_domains"]
    seeds={norm(x).rstrip("/") for x in o["seed_urls"]}
    def first_party(host):
        return any(host==h or host.endswith("."+h) for h in primary)
    for f in pages:
        source=norm(f.get("final","")).rstrip("/")
        host=hostname(source)
        if not (first_party(host) or any(source==seed or source.startswith(seed+"/") for seed in seeds)):
            continue
        urls=[source] if source in seeds else []
        if first_party(host):
            soup=BeautifulSoup(f.get("html") or "","html.parser")
            urls.extend(urljoin(f["final"],a["href"]) for a in soup.find_all("a",href=True))
        for u in urls:
            p=urlparse(u); h=hostname(u); parts=[x for x in p.path.split("/") if x]
            if not parts:continue
            token=parts[0]
            if token.lower() in ("jobs","job","careers","positions","search","en","nl"):continue
            config=None
            if h in ("job-boards.greenhouse.io","boards.greenhouse.io",
                     "job-boards.eu.greenhouse.io","boards.eu.greenhouse.io"):
                region="eu." if ".eu.greenhouse.io" in h else ""
                config={"type":"greenhouse",
                        "url":f"https://boards-api.{region}greenhouse.io/v1/boards/{token}/jobs",
                        "board":f"https://{p.netloc}/{token}"}
            elif h in ("jobs.lever.co","jobs.eu.lever.co"):
                region="eu." if h=="jobs.eu.lever.co" else ""
                config={"type":"lever","url":f"https://api.{region}lever.co/v0/postings/{token}",
                        "board":f"https://{p.netloc}/{token}"}
            elif h in ("careers.smartrecruiters.com","jobs.smartrecruiters.com"):
                config={"type":"smartrecruiters",
                        "url":f"https://api.smartrecruiters.com/v1/companies/{token}/postings",
                        "board":f"https://jobs.smartrecruiters.com/{token}"}
            if config and config["url"] not in seen:
                seen.add(config["url"]);configs.append(config)
    return configs


def api_inventory(o,c=None):
    """Exhaust the configured or officially discovered ATS feed. Partial data is never complete."""
    c=c or API_BOARDS.get(o["name"])
    if not c:return None
    items=[]; official_total=None; pages=0; terminal=False; source=c["url"]
    try:
        def get_json(url,params=None):
            response=requests.get(url,headers=H,params=params,timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        if c["type"]=="workday":
            # Workday public CXS API. Design adapted from the MIT-licensed
            # kalil0321/ats-scrapers Workday adapter, with stricter fail-closed
            # completeness semantics for this monitor.
            WD_LIMIT=20; WD_CAP=2000; WD_RETRIES=4
            retryable={403,429,502,503,504}
            def wd_request(facets,offset):
                nonlocal pages
                body={"limit":WD_LIMIT,"offset":offset,"searchText":"","appliedFacets":facets}
                last=None
                for attempt in range(WD_RETRIES):
                    try:
                        rr=requests.post(source,headers=H,json=body,timeout=TIMEOUT)
                        if rr.status_code in retryable:
                            last=ValueError(f"Workday transient HTTP {rr.status_code}")
                            if attempt+1<WD_RETRIES:
                                wait=rr.headers.get("Retry-After")
                                delay=min(5.0,float(wait)) if wait and str(wait).isdigit() else min(5.0,2**attempt)
                                time.sleep(delay);continue
                            raise last
                        rr.raise_for_status()
                        try: d=rr.json()
                        except ValueError:
                            last=ValueError("Workday returned non-JSON success response")
                            if attempt+1<WD_RETRIES:
                                time.sleep(min(5.0,2**attempt));continue
                            raise last
                        if not isinstance(d,dict) or not isinstance(d.get("total"),int) or not isinstance(d.get("jobPostings"),list):
                            raise ValueError("Workday response missing total/jobPostings")
                        pages+=1
                        return d
                    except requests.RequestException as exc:
                        last=exc
                        if attempt+1<WD_RETRIES:
                            time.sleep(min(5.0,2**attempt));continue
                        raise
                raise last or ValueError("Workday request failed")

            def wd_key(j):
                path=j.get("externalPath") or ""
                ident=re.search(r"_([A-Z]{2,8}[0-9]{4,}[A-Z0-9]*)$",path)
                return ident.group(1) if ident else path

            def wd_pick_facet(payload,used):
                by={}
                for facet in payload.get("facets") or []:
                    if not isinstance(facet,dict):continue
                    param=facet.get("facetParameter"); vals=facet.get("values") or []
                    if not param or param in used:continue
                    good=[(v.get("id"),int(v.get("count") or 0)) for v in vals
                          if isinstance(v,dict) and v.get("id") and int(v.get("count") or 0)>0]
                    if len(good)>=2:by[param]=good
                for preferred in ("jobFamilyGroup","timeType","locations","workerSubType"):
                    if preferred in by:return preferred,by[preferred]
                return max(by.items(),key=lambda kv:len(kv[1])) if by else None

            collected={}
            def absorb(postings):
                for j in postings:
                    if not isinstance(j,dict):raise ValueError("Workday posting has invalid type")
                    key=wd_key(j)
                    if not key:raise ValueError("Workday posting missing stable identity")
                    collected[key]=j

            def exhaust(facets,depth=0):
                first=wd_request(facets,0)
                total=first["total"]; postings=first["jobPostings"]
                if len(postings)>WD_LIMIT:raise ValueError("Workday page overfilled")
                absorb(postings)
                if total==0:return 0
                if not postings:raise ValueError("Workday empty first page with positive total")
                if total==WD_CAP:
                    if depth>=4:raise ValueError("Workday 2000-result cap unresolved at max subdivision depth")
                    choice=wd_pick_facet(first,set(facets))
                    if not choice:raise ValueError("Workday 2000-result cap unresolved: no partition facet")
                    param,values=choice
                    for value,_count in values:
                        exhaust({**facets,param:[value]},depth+1)
                    return None
                if total>WD_CAP:raise ValueError("Workday total exceeds supported query cap")
                seen_page={wd_key(j) for j in postings}
                for offset in range(WD_LIMIT,total,WD_LIMIT):
                    batch=wd_request(facets,offset)
                    more=batch["jobPostings"]
                    # Some tenants return total=0 on continuation pages. The
                    # first page remains authoritative for this partition.
                    if batch["total"] not in (total,0):
                        raise ValueError("Workday total changed during pagination")
                    if not more or len(more)>WD_LIMIT:
                        raise ValueError("Workday pagination stopped early or overfilled")
                    keys={wd_key(j) for j in more}
                    if not keys or keys.issubset(seen_page):
                        raise ValueError("Workday page-wrap/repeated page detected")
                    seen_page.update(keys);absorb(more)
                if len(seen_page)!=total:
                    raise ValueError(f"Workday unique count mismatch: {len(seen_page)} != {total}")
                return total

            root_total=exhaust({})
            raw=list(collected.values())
            # For an uncapped root, the official total must reconcile exactly.
            # For a successfully partitioned capped root, every child partition
            # was independently exhausted; the deduplicated union is the proof.
            official_total=root_total if root_total is not None else len(raw)
            if root_total is not None and len(raw)!=root_total:
                raise ValueError("Workday root inventory did not reconcile")
            for j in raw:
                path=j.get("externalPath") or "";title=j.get("title") or ""
                if not title or not path.startswith("/job/"):
                    raise ValueError("Workday posting missing title/externalPath")
                ident=re.search(r"_([A-Z]{2,8}[0-9]{4,}[A-Z0-9]*)$",path)
                items.append({"title":title,"url":c["board"].rstrip("/")+path,
                              "workday_detail_url":source.rsplit("/jobs",1)[0]+path,
                              "workday_job_id":ident.group(1) if ident else None})
            terminal=True
        elif c["type"]=="breezy":
            raw=get_json(source);pages=1
            if not isinstance(raw,list):raise ValueError("Expected Breezy positions list")
            official_total=len(raw)
            for j in raw:
                title=j.get("name") or j.get("title") or "";u=j.get("url") or ""
                if title and u:items.append({"title":title,"url":u})
            terminal=True
        elif c["type"]=="greenhouse":
            # Public Greenhouse board endpoints return an entire jobs array;
            # meta.total is optional rather than a required pagination counter.
            d=get_json(source);pages=1
            if not isinstance(d,dict) or not isinstance(d.get("jobs"),list):
                raise ValueError("Greenhouse jobs array absent")
            raw=d["jobs"]
            meta=d.get("meta")
            if meta is not None and not isinstance(meta,dict):
                raise ValueError("Greenhouse meta has invalid type")
            if isinstance(meta,dict) and "total" in meta:
                official_total=meta["total"]
                if type(official_total) is not int or official_total<0:
                    raise ValueError("Greenhouse official total invalid")
            if not raw and official_total is None:
                raise ValueError("Empty Greenhouse feed without independent board-total evidence")
            for j in raw:
                if not isinstance(j,dict):
                    raise ValueError("Greenhouse posting has invalid type")
                title=j.get("title") or "";u=j.get("absolute_url") or ""
                if not title or not u:
                    raise ValueError("Greenhouse posting missing title or URL")
                items.append({"title":title,"url":u})
            terminal=True
        elif c["type"]=="lever":
            # Lever documents skip/limit pagination, with no global total field.
            # A final short/empty page is proof of exhaustion, not an invented official total.
            limit=100;raw=[];offset=0
            for _ in range(30):
                batch=get_json(source,{"mode":"json","skip":offset,"limit":limit});pages+=1
                if not isinstance(batch,list):raise ValueError("Lever returned non-list")
                raw.extend(batch);offset+=len(batch)
                if len(batch)<limit:
                    terminal=True;break
            for j in raw:
                title=j.get("text") or "";u=j.get("hostedUrl") or ""
                if title and u:items.append({"title":title,"url":u})
        elif c["type"]=="ashby":
            d=get_json(source);pages=1
            if not isinstance(d,dict) or not isinstance(d.get("jobs"),list) or not d.get("apiVersion"):
                raise ValueError("Unexpected Ashby published-posting schema")
            raw=[j for j in d["jobs"] if j.get("isListed") is not False]
            official_total=len(raw)
            for j in raw:
                title=j.get("title") or ""
                official=airwallex_official_url(j)
                if title and official:
                    items.append({"title":title,"url":official,"source_job_id":airwallex_id(official),
                                  "ats_url":j["jobUrl"],"location":j.get("location") or "",
                                  "department":j.get("department") or "","team":j.get("team") or "",
                                  "published_at":j.get("publishedAt")})
            terminal=True
        elif c["type"]=="recruitee":
            d=get_json(source);pages=1
            if not isinstance(d,dict) or not isinstance(d.get("offers"),list):
                raise ValueError("Recruitee offers array absent")
            raw=d["offers"];official_total=len(raw);identities=set()
            for j in raw:
                if not isinstance(j,dict):raise ValueError("Recruitee offer has invalid type")
                title=j.get("title") or "";slug=j.get("slug") or "";ident=j.get("id")
                stable=str(ident) if ident is not None else str(slug)
                u=j.get("careers_url") or j.get("careers_apply_url") or (c["board"].rstrip("/")+"/o/"+str(slug) if slug else "")
                if not title or not u or not stable:raise ValueError("Recruitee offer missing required publication fields")
                if stable in identities:raise ValueError("Duplicate Recruitee offer identity")
                identities.add(stable)
                items.append({"title":title,"url":u,"source_job_id":stable,
                              "department":j.get("department") or "","location":j.get("location") or ""})
            terminal=True
        elif c["type"]=="smartrecruiters":
            limit=100;raw=[];offset=0
            for _ in range(30):
                d=get_json(source,{"limit":limit,"offset":offset,"destination":"PUBLIC"});pages+=1
                if not isinstance(d,dict) or not isinstance(d.get("totalFound"),int) or not isinstance(d.get("content"),list):
                    raise ValueError("SmartRecruiters totalFound/content absent")
                if official_total is None:official_total=d["totalFound"]
                if d["totalFound"]!=official_total:raise ValueError("SmartRecruiters total changed")
                batch=d["content"];raw.extend(batch);offset+=len(batch)
                if offset>=official_total:
                    terminal=True;break
                if not batch:raise ValueError("SmartRecruiters pagination stopped early")
            for j in raw:
                title=j.get("name") or "";ident=j.get("id") or ""
                u=j.get("jobAdUrl") or j.get("postingUrl") or (c["board"].rstrip("/")+"/"+str(ident) if ident else "")
                if title and u:
                    item={"title":title,"url":u}
                    if o["name"]=="Wise":
                        item.update({"smartrecruiters_posting_id":str(ident),
                                     "smartrecruiters_detail_url":source.rstrip("/")+"/"+str(ident),
                                     "posting_uuid":j.get("uuid"),
                                     "location":j.get("location",{}).get("city","") if isinstance(j.get("location"),dict) else "",
                                     "published_at":j.get("releasedDate")})
                    items.append(item)
        else:raise ValueError("Unknown ATS type")
        urls=[j["url"] for j in items]
        # A board may return employer-hosted links, but never accept a foreign employer.
        if any(not allowed(u,o) or not (u.startswith(c["board"]) or hostname(u)==hostname(o["seed_urls"][0]) or
                    hostname(u)==o["official_domain"] or hostname(u).endswith("."+o["official_domain"]) or
                    any(hostname(u)==d or hostname(u).endswith("."+d) for d in o["allowed_domains"]))
               for u in urls):
            raise ValueError("ATS returned an unrelated employer or board URL")
        unique={job_key(j["url"]):j for j in items}
        expected=official_total if official_total is not None else len(items)
        complete=bool(terminal and len(items)==len(unique)==expected)
        if c["type"]=="lever" and not terminal:complete=False
        if c["type"]=="ashby" and not official_total:complete=False
        return {"complete":complete,"official_total":official_total,"jobs":list(unique.values()),
                "source":source,"pages":pages,"terminal":terminal,
                "evidence_kind":"official_api_total" if official_total is not None else "official_api_exhausted",
                "error":None if complete else "Incomplete or duplicate ATS listing"}
    except Exception as e:
        return {"complete":False,"official_total":official_total,"jobs":[],"source":source,
                "pages":pages,"terminal":False,"evidence_kind":"api_failure",
                "error":f"{type(e).__name__}: {e}"}

def static_inventory(o):
    """Exhaust small official boards, including explicit ?page=N pagination, before proving completeness."""
    c=STATIC_BOARDS.get(o["name"])
    if not c: return None
    try:
        queue=[c["url"]]; seen=set(); jobs={}; rx=re.compile(c["href"],re.I); source=c["url"]; terminal=True
        while queue and len(seen)<25:
            page=queue.pop(0)
            if page in seen: continue
            seen.add(page)
            rr=requests.get(page,headers=H,timeout=TIMEOUT,allow_redirects=True); rr.raise_for_status(); source=rr.url
            soup=BeautifulSoup(rr.text,"html.parser")
            for a in soup.find_all("a",href=True):
                u=norm(urljoin(rr.url,a["href"]))
                if rx.search(urlparse(u).path):
                    title=a.get_text(" ",strip=True)
                    if not title or re.fullmatch(r"(lees meer|read more|bekijk vacature|view vacancy|view job|more)",title,re.I):
                        box=a.find_parent(["article","li","section","div"])
                        if box:
                            h=box.find(["h1","h2","h3","h4","h5"])
                            if h: title=h.get_text(" ",strip=True)
                    if not title or len(title)<4:
                        slug=urlparse(u).path.rstrip("/").split("/")[-1]
                        title=re.sub(r"[-_]+"," ",slug).strip().title()
                    jobs[u]={"title":title,"url":u}
                pp=urlparse(u); q=parse_qs(pp.query)
                if hostname(u)==hostname(rr.url) and q.get("page") and u not in seen and u not in queue:
                    queue.append(u)
            nxt=soup.find("a",attrs={"rel":lambda v:v and "next" in str(v).lower()})
            if nxt and nxt.get("href"):
                u=norm(urljoin(rr.url,nxt["href"]))
                if allowed(u,o) and u not in seen and u not in queue: queue.append(u)
            labels=" ".join(x.get_text(" ",strip=True) for x in soup.find_all(["a","button"]))
            if DYNAMIC_MORE.search(labels):
                terminal=False
        if queue: terminal=False
        return {"complete":bool(jobs and terminal),"official_total":len(jobs),"jobs":list(jobs.values()),"source":source,
                "pages":len(seen),"error":None if jobs else "No vacancy links found"}
    except Exception as e:
        return {"complete":False,"official_total":None,"jobs":[],"source":c["url"],"error":f"{type(e).__name__}: {e}"}

def candidates(o):
    q=list(o["seed_urls"]); base=origin(q[0])
    q += [base.rstrip("/")+p for p in COMMON]
    return list(dict.fromkeys(q))

def links(f,o):
    if not f["html"]: return []
    s=BeautifulSoup(f["html"],"html.parser"); z=[]
    for a in s.find_all("a",href=True):
        u=norm(urljoin(f["final"],a["href"])); lab=a.get_text(" ",strip=True)
        if u.startswith("http") and allowed(u,o) and (isats(u) or CAREER.search(lab+" "+u)):
            z.append(u)
    # Listing/search pages first. A careers blog must not exhaust the crawl budget.
    z=list(dict.fromkeys(z))
    z.sort(key=lambda u:(0 if re.search(r"(search|vacanc|jobs|openings|positions|listing)",u,re.I) else 1,u))
    return z[:25]

def search_official(o):
    u="https://html.duckduckgo.com/html/?q="+quote_plus(f'site:{o["official_domain"]} "{o["name"]}" jobs careers vacancies')
    f=fetch(u,"search-discovery")
    if not f["ok"]: return []
    s=BeautifulSoup(f["html"],"html.parser"); out=[]
    for a in s.select("a.result__a"):
        u=norm(a.get("href",""))
        if u.startswith("http") and allowed(u,o): out.append(u)
    return list(dict.fromkeys(out))[:6]

def inventory_url(u):
    """Exclude navigation paths, not employer hostnames or vacancy title words."""
    path=urlparse(u).path
    return bool(JOBURL.search(path)) and not re.search(
        r"/(?:search|search-results|search-jobs|job-search|filter|login|privacy|data-privacy|cookie-policy|alert|subscribe|blog|article)(?:/|$)",path,re.I)

def listing_evidence(f,o):
    """Evidence for whether an official public listing is exhaustively visible."""
    s=BeautifulSoup(f["html"],"html.parser")
    links=[]
    for a in s.find_all("a",href=True):
        u=norm(urljoin(f["final"],a["href"]))
        title=a.get_text(" ",strip=True)
        if 4<=len(title)<=180 and allowed(u,o) and JOBURL.search(u) and not PAGING.search(title):
            if inventory_url(u):
                links.append(u)
    unique=set(links)
    forward=bool(s.find(attrs={"rel":"next"}) or any(PAGING.search(a.get_text(" ",strip=True)) for a in s.find_all("a",href=True)))
    buttons=" ".join(x.get_text(" ",strip=True) for x in s.find_all(["button","a"]))
    dynamic=bool(DYNAMIC_MORE.search(buttons))
    path=urlparse(f["final"]).path
    listing_like=bool(LISTING_URL.search(f["final"]) or (len(unique)>=5 and not re.search(r"/jobs?/[^/?#]+",path,re.I)))
    text=s.get_text(" ",strip=True)
    totals=[]
    for m in re.finditer(r"\b([0-9]{1,5})\s+(?:open\s+)?(?:jobs?|vacatures?|positions?|roles?|results?|offres?)\b",text,re.I):
        n=int(m.group(1))
        if n>=len(unique): totals.append(n)
    official_total=max(totals) if totals else None
    complete=bool(listing_like and unique and not forward and not dynamic and official_total is not None and len(unique)==official_total)
    return {"url":f["final"],"job_link_count":len(unique),"pagination_seen":forward,
            "dynamic_more_seen":dynamic,"listing_like":listing_like,"official_total":official_total,
            "static_complete_evidence":complete}

def coverage_from_evidence(evidence,o):
    """Keep reachability separate from proof that the public inventory is exhaustive."""
    if not evidence:
        return "unproven"
    if any(e.get("static_complete_evidence") for e in evidence):
        return "verified_complete"
    listing=[e for e in evidence if e.get("job_link_count")]
    if o["no_public_hint"] and not listing:
        return "verified_no_public_board"
    return "partial" if listing else "unproven"

def audit_candidates(f,o):
    """Independent broad title/url sweep used to estimate matcher recall."""
    if not f["html"]: return []
    soup=BeautifulSoup(f["html"],"html.parser"); out=[]
    for a in soup.find_all("a",href=True):
        title=a.get_text(" ",strip=True); u=norm(urljoin(f["final"],a["href"]))
        if 4<=len(title)<=180 and u.startswith("http") and allowed(u,o) and JOBURL.search(u):
            hay=title+" "+u
            if AUDIT_REL.search(hay) and AUDIT_SENIOR.search(title):
                out.append({"title":title,"url":u})
    d={(j["title"].lower(),j["url"]):j for j in out}
    return list(d.values())

def extract_jobs(f,o):
    if not f["html"]: return []
    s=BeautifulSoup(f["html"],"html.parser"); out=[]
    for a in s.find_all("a",href=True):
        title=a.get_text(" ",strip=True); u=norm(urljoin(f["final"],a["href"]))
        if 4<=len(title)<=180 and u.startswith("http") and allowed(u,o) and JOBURL.search(u) and REL.search(title+" "+u) and (SENIOR.search(title) or re.search(r"\b(mlro|cco|cro|sanctions counsel|regulatory counsel)\b", title, re.I)):
            out.append({"title":title,"url":u})
    # Some job boards render cards through scripts but expose schema.org data.
    for tag in s.select('script[type="application/ld+json"]'):
        try: payload=json.loads(tag.string or tag.get_text())
        except (ValueError,TypeError): continue
        stack=[payload]
        while stack:
            item=stack.pop()
            if isinstance(item,list): stack.extend(item); continue
            if not isinstance(item,dict): continue
            stack.extend(v for v in item.values() if isinstance(v,(dict,list)))
            types=item.get("@type",[]); types=[types] if isinstance(types,str) else types
            if "JobPosting" not in types: continue
            title=item.get("title",""); raw_url=item.get("url","")
            if not isinstance(title,str) or not isinstance(raw_url,str) or not raw_url: continue
            u=urljoin(f["final"],raw_url)
            if allowed(u,o) and REL.search(title) and SENIOR.search(title):
                out.append({"title":title,"url":u})
    d={}
    for j in out: d[(j["title"].lower(),j["url"])]=j
    return list(d.values())[:100]

def board_job_keys_from_pages(pages,o):
    """Current-board evidence: vacancy links exposed by an official listing/careers page."""
    keys=set()
    seeds={norm(x).rstrip("/") for x in o["seed_urls"]}
    for f in pages:
        found=inventory_job_links(f["html"],f["final"],o)
        ev=listing_evidence(f,o)
        source=norm(f["final"]).rstrip("/")
        # Accept a declared seed/listing page, or a page that currently exposes multiple job links.
        if source in seeds or ev.get("listing_like") or len(found)>=2:
            keys.update(job_key(u) for u in found)
    return keys

def has_apply_control(html):
    """Only count an enabled application link or button, not generic 'Apply' text."""
    soup=BeautifulSoup(html or "","html.parser")
    for el in soup.find_all(["a","button","input"]):
        label=(el.get_text(" ",strip=True) or el.get("aria-label") or el.get("value") or "").strip()
        if not APPLY.search(label):continue
        if el.has_attr("disabled") or str(el.get("aria-disabled","")).lower()=="true":continue
        if el.name=="input" and str(el.get("type","")).lower() not in ("submit","button"):continue
        if el.name=="a":
            href=str(el.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):continue
        return True
    return False

def validate_workday_candidate(j,board_keys):
    """Require live official Workday detail, matching requisition and working apply route."""
    out=dict(j);requested=j["url"]
    board_present=job_key(requested) in board_keys
    direct_live=False;apply_route=False;status=None;final=requested;reason="detail_page_not_live"
    try:
        api_url=j["workday_detail_url"]
        response=requests.get(api_url,headers=H,timeout=TIMEOUT,allow_redirects=True)
        status=response.status_code
        data=response.json() if status==200 else {}
        info=data.get("jobPostingInfo") if isinstance(data,dict) else None
        if isinstance(info,dict):
            title_match=str(info.get("title","")).strip().casefold()==j["title"].strip().casefold()
            id_match=bool(j.get("workday_job_id") and info.get("jobReqId")==j["workday_job_id"])
            official_path=urlparse(info.get("externalUrl") or "").path
            path_match=official_path==urlparse(requested).path
            direct_live=bool(title_match and id_match and path_match and info.get("canApply") is True)
        if direct_live and board_present:
            apply_url=requested.rstrip("/")+"/apply"
            apply_response=requests.get(apply_url,headers=H,timeout=TIMEOUT,allow_redirects=True)
            apply_route=bool(apply_response.status_code==200 and
                             urlparse(apply_response.url).path.rstrip("/")==urlparse(apply_url).path.rstrip("/"))
        else:
            apply_url=None
        if direct_live and board_present and apply_route:reason="direct_live_and_current_board"
        elif not board_present:reason="not_on_current_board"
        elif direct_live and not apply_route:reason="no_live_apply_control"
    except Exception as exc:
        reason="workday_detail_or_apply_error:"+type(exc).__name__
        apply_url=None
    out.update({"url":final,"live":direct_live,"board_present":board_present,
                "apply_live":bool(direct_live and board_present and apply_route),
                "validation_reason":reason,"http_status":status,"checked_at":iso(),
                "validation_source":"official_workday_detail_and_apply",
                "apply_url":apply_url})
    return out


def validate_embedded_candidate(j,board_keys):
    """Strict ID, current official index, exact title, live detail and application path."""
    item=dict(j); ident=str(j["embedded_job_id"]).lower();provider=j["embedded_provider"]
    requested=j["url"];detail=fetch(requested,"job-live-check")
    path=urlparse(detail["final"]).path.rstrip("/").lower()
    host=hostname(detail["final"])
    if provider=="N26":
        identity=bool(host=="n26.com" and path=="/en-eu/careers/positions/"+ident)
        apply_url="https://n26.com/en-eu/careers/positions/"+ident+"/apply"
    else:
        identity=bool(host in ("revolut.com","www.revolut.com") and
                      path.startswith("/careers/position/") and path.endswith("-"+ident))
        apply_url="https://www.revolut.com/careers/apply/"+ident+"/"
    soup=BeautifulSoup(detail["html"],"html.parser")
    h1=soup.find("h1");actual_title=h1.get_text(" ",strip=True) if h1 else ""
    title_ok=re.sub(r"\s+"," ",actual_title).casefold()==re.sub(r"\s+"," ",j["title"]).casefold()
    board_present=job_key(requested) in board_keys
    direct_live=bool(detail["ok"] and identity and title_ok and not CLOSED.search(detail["text"]))
    link_ok=any(
        APPLY.search(a.get_text(" ",strip=True)) and
        urlparse(urljoin(detail["final"],a.get("href",""))).path.rstrip("/")==urlparse(apply_url).path.rstrip("/")
        and hostname(urljoin(detail["final"],a.get("href","")))==hostname(apply_url)
        for a in soup.find_all("a",href=True)
    )
    apply_route=False;apply_http_status=None
    if direct_live and board_present and link_ok:
        check=fetch(apply_url,"apply-live-check");apply_http_status=check["status"]
        asoup=BeautifulSoup(check["html"],"html.parser")
        path_ok=(hostname(check["final"])==hostname(apply_url) and
                 urlparse(check["final"]).path.rstrip("/")==urlparse(apply_url).path.rstrip("/"))
        if provider=="Revolut":
            form_ok=bool(asoup.find("form") and asoup.find("input"))
        else:
            form_ok=bool(asoup.title and j["title"].casefold() in asoup.title.get_text(" ",strip=True).casefold())
        apply_route=bool(check["ok"] and path_ok and ident in check["html"].lower() and form_ok)
    apply_live=bool(direct_live and board_present and link_ok and apply_route)
    if apply_live:reason="direct_live_and_current_board"
    elif detail["status"]==429:reason="rate_limited"
    elif detail["status"]==403:reason="access_blocked"
    elif not board_present:reason="not_on_current_board"
    elif not direct_live:reason="detail_page_not_live"
    else:reason="no_live_apply_control"
    item.update({"url":detail["final"],"live":direct_live,"board_present":board_present,
                 "apply_live":apply_live,"validation_reason":reason,"http_status":detail["status"],
                 "checked_at":iso(),"apply_url":apply_url,"apply_http_status":apply_http_status,
                 "validation_source":"first_party_embedded_index_and_direct_apply"})
    return item


def validate_wise_candidate(j,board_keys):
    """Verify Wise's published ATS posting and the same posting's active application."""
    item=dict(j);requested=j["url"];ident=str(j.get("smartrecruiters_posting_id") or "")
    uuid=str(j.get("posting_uuid") or "").lower()
    board_present=bool(job_key(requested) in board_keys)
    detail_live=False;apply_route=False;detail_status=None;apply_status=None
    reason="detail_page_not_live";first_party_detail=None
    expected_host="jobs.smartrecruiters.com"
    def posting_path_ok(url):
        path=urlparse(url).path
        return bool(hostname(url)==expected_host and
                    re.match(r"^/Wise/"+re.escape(ident)+r"(?:-|/|$)",path,re.I))
    def exact_title(html):
        soup=BeautifulSoup(html or "","html.parser")
        title=soup.title.get_text(" ",strip=True) if soup.title else ""
        return bool(j["title"].casefold() in title.casefold())
    try:
        api=requests.get(j["smartrecruiters_detail_url"],headers=H,timeout=TIMEOUT)
        if api.status_code==200 and hostname(api.url)=="api.smartrecruiters.com":
            d=api.json()
            ats_url=d.get("postingUrl") or ""
            apply_url=d.get("applyUrl") or ""
            api_ok=bool(str(d.get("id"))==ident and
                        str(d.get("name") or "").strip().casefold()==j["title"].strip().casefold() and
                        str(d.get("uuid") or "").lower()==uuid and
                        re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",uuid) and
                        posting_path_ok(ats_url) and posting_path_ok(apply_url))
            if api_ok and board_present:
                page=fetch(requested,"job-live-check")
                detail_status=page["status"]
                detail_live=bool(page["ok"] and posting_path_ok(page["final"]) and
                                 exact_title(page["html"]) and not CLOSED.search(page["text"]))
                first_party_detail=page["final"]
                if detail_live:
                    # The official public API supplies the application route. The
                    # same UUID must resolve to Wise's actual one-click application.
                    redirect=fetch(apply_url,"apply-live-check")
                    oneclick_url=("https://jobs.smartrecruiters.com/oneclick-ui/company/Wise/publication/"
                                  +uuid+"?dcr_ci=Wise")
                    publication_path=("/oneclick-ui/company/wise/publication/"+uuid).lower()
                    redirected_path=urlparse(redirect["final"]).path.rstrip("/").lower()
                    redirect_is_publication=(hostname(redirect["final"])==expected_host and
                                             redirected_path==publication_path)
                    # SmartRecruiters ?oga=true legitimately redirects straight to its
                    # one-click form. Reject a generic board or a different publication.
                    form=redirect if redirect_is_publication else fetch(oneclick_url,"apply-live-check")
                    apply_status=form["status"]
                    path=urlparse(form["final"]).path.rstrip("/").lower()
                    same_publication=path==publication_path
                    apply_route=bool(redirect["ok"] and
                                     (posting_path_ok(redirect["final"]) or redirect_is_publication) and
                                     exact_title(redirect["html"]) and
                                     form["ok"] and hostname(form["final"])==expected_host and
                                     same_publication and exact_title(form["html"]) and
                                     not CLOSED.search(form["text"]))
            if detail_live and board_present and apply_route:reason="direct_live_and_current_board"
            elif not board_present:reason="not_on_current_board"
            elif detail_live:reason="no_live_apply_control"
        if api.status_code==404:reason="detail_page_not_live"
    except Exception as exc:
        reason="smartrecruiters_detail_or_apply_error:"+type(exc).__name__
    item.update({"url":first_party_detail or requested,"live":detail_live,"board_present":board_present,
                 "apply_live":bool(detail_live and board_present and apply_route),
                 "validation_reason":reason,"http_status":detail_status,"checked_at":iso(),
                 "validation_source":"official_smartrecruiters_listing_detail_and_application",
                 "apply_http_status":apply_status})
    return item


def validate_jobs(js,board_keys=None,max_workers=6):
    """Live-check every candidate in bounded parallel requests; never infer liveness from a board alone."""
    board_keys=set(board_keys or ())
    def verify(candidate):
        j=dict(candidate)
        if j.get("workday_detail_url"):
            return validate_workday_candidate(j,board_keys)
        if j.get("smartrecruiters_detail_url") and j.get("posting_uuid"):
            return validate_wise_candidate(j,board_keys)
        if j.get("embedded_provider") in ("N26","Revolut"):
            return validate_embedded_candidate(j,board_keys)
        requested=j["url"]; f=fetch(requested,"job-live-check"); text=f["text"]
        identity_ok=not j.get("source_job_id") or airwallex_id(f["final"])==j["source_job_id"]
        direct_live=f["ok"] and identity_ok and (j["title"].lower()[:24] in text.lower() or len(j["title"])<12)
        board_present=job_key(requested) in board_keys or job_key(f["final"]) in board_keys
        apply_live=bool(direct_live and board_present and has_apply_control(f["html"]) and not CLOSED.search(text))
        if apply_live: reason="direct_live_and_current_board"
        elif f["status"]==429: reason="rate_limited"
        elif f["status"]==403: reason="access_blocked"
        elif not board_present: reason="not_on_current_board"
        elif not direct_live: reason="detail_page_not_live"
        elif CLOSED.search(text): reason="closed_marker"
        else: reason="no_live_apply_control"
        j.update({"url":f["final"],"live":direct_live,"board_present":board_present,"apply_live":apply_live,
                  "validation_reason":reason,"http_status":f["status"],"checked_at":iso()})
        return j
    if not js: return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers,len(js))) as ex:
        return list(ex.map(verify,js))

def airwallex_validation_queue(jobs,capacity=25,priority_count=20):
    """Prioritise senior EU/UK financial-crime leadership; rotate the remainder.
    Retain every other ATS candidate as pending, never pretend it was checked.
    """
    def priority(j):
        title=j["title"].lower(); loc=str(j.get("location","")).lower()
        score=0
        if re.search(r"aml|sanction|financial.crime|mlro|fcc|risk assurance",title):score+=12
        if re.search(r"amsterdam|netherlands|nl -",loc):score+=10
        elif re.search(r"london|united kingdom|uk -|emea|europe|remote",loc):score+=8
        if re.search(r"director|head|chief|mlro|vice.president",title):score+=6
        if re.search(r"operational kyc|customer support|sales|account manager",title):score-=10
        return score
    ordered=sorted(jobs,key=lambda j:(-priority(j),j.get("source_job_id") or j["url"]))
    fixed=ordered[:min(priority_count,capacity)]
    tail=ordered[len(fixed):]
    count=capacity-len(fixed)
    if count and tail:
        offset=(datetime.now(ZoneInfo("Europe/Amsterdam")).date().toordinal()*count)%len(tail)
        rotating=[tail[(offset+i)%len(tail)] for i in range(min(count,len(tail)))]
    else:rotating=[]
    chosen=fixed+rotating
    picked={j["source_job_id"] for j in chosen}
    deferred=[{**j,"live":False,"board_present":True,"apply_live":False,
               "validation_reason":"pending_direct_validation","http_status":None,"checked_at":None}
              for j in jobs if j["source_job_id"] not in picked]
    return chosen,deferred


def scan(o):
    t=time.monotonic(); tried=[]; success=[]; q=candidates(o); seen=set()
    configured_api=api_inventory(o); api_attempts=[configured_api] if configured_api else []
    api=configured_api; static=static_inventory(o)
    # Published ATS enumeration replaces unfocused first-party crawling for
    # Airwallex. The first-party seed and candidate detail pages are still read.
    if o["name"]=="Airwallex" and api and api.get("complete"):
        q=list(o["seed_urls"])
    while q and len(seen)<(4 if o["name"]=="Airwallex" and api and api.get("complete") else 24):
        u=q.pop(0)
        if u in seen: continue
        seen.add(u); f=fetch(u)
        tried.append({k:f[k] for k in ("url","final","method","status","ok","error","ms")})
        if f["ok"] and allowed(f["final"],o):
            success.append(f)
            for x in links(f,o):
                if x not in seen and x not in q: q.append(x)
    if not success:
        for u in search_official(o):
            f=fetch(u,"search-discovered-official")
            tried.append({k:f[k] for k in ("url","final","method","status","ok","error","ms")})
            if f["ok"] and allowed(f["final"],o): success.append(f); break
    # Discover provider feeds from pages actually linked by the official employer.
    # A broken configured endpoint cannot prevent checking an officially linked replacement.
    if not (api and api["complete"]):
        for config in discover_official_ats(success,o)[:4]:
            if config["url"] in {x["source"] for x in api_attempts}:continue
            result=api_inventory(o,config);api_attempts.append(result)
            if result["complete"]:
                api=result;break
    embedded=None
    if o["name"] in ("N26","Revolut"):
        for f in success:
            found=embedded_inventory(o["name"],f["html"],f["final"])
            if found and (embedded is None or len(found["jobs"])>len(embedded["jobs"])):
                embedded=found
            if embedded and embedded["complete"]:break
    js=[]; [js.extend(extract_jobs(f,o)) for f in success]
    raw_matches=list({(j["title"].lower(),j["url"]):j for j in js}.values())
    audits=[]; [audits.extend(audit_candidates(f,o)) for f in success]
    audit_unique=list({(j["title"].lower(),j["url"]):j for j in audits}.values())
    matched_urls={j["url"] for j in raw_matches}
    audit_missed=[j for j in audit_unique if j["url"] not in matched_urls]
    board_keys=board_job_keys_from_pages(success,o)
    jobs=validate_jobs(raw_matches,board_keys)
    evidence=[listing_evidence(f,o) for f in success]
    if success:
        if o["no_public_hint"] and not jobs: st="no_public_vacancy_board"
        elif any(isats(f["final"]) for f in success): st="official_ats_scanned"
        elif any(CAREER.search(f["final"]+" "+f["text"][:12000]) for f in success): st="official_site_scanned"
        else: st="no_public_vacancy_board" if o["no_public_hint"] else "technical_failure"
    else: st="technical_failure"
    coverage=coverage_from_evidence(evidence,o)
    for checked_api in api_attempts:
        evidence.append({"url":checked_api["source"],"api_complete":checked_api["complete"],
                         "official_total":checked_api["official_total"],"job_link_count":len(checked_api["jobs"]),
                         "listing_like":True,"static_complete_evidence":checked_api["complete"] and o["name"] not in ("Airwallex","Wise"),
                         "api_pages":checked_api["pages"],"api_terminal":checked_api["terminal"],
                         "evidence_kind":checked_api["evidence_kind"],"api_error":checked_api["error"]})
    if api and api.get("complete"):
        # The Ashby published feed is complete as an ATS source, but the
        # separate Airwallex first-party catalogue has a different total.
        # Do not claim complete overall Airwallex coverage until reconciled.
        coverage="partial" if o["name"] in ("Airwallex","Wise") else "verified_complete"
        st="official_ats_scanned"
        api_raw=([j for j in api["jobs"] if strategic_inventory_match(j)]
                 if o["name"]=="Airwallex" else
                 [j for j in api["jobs"] if REL.search(j["title"]+" "+j["url"]) and
                  (SENIOR.search(j["title"]) or re.search(r"\b(mlro|cco|cro|sanctions counsel|regulatory counsel)\b",j["title"],re.I))])
        api_audit=[j for j in api["jobs"] if AUDIT_SENIOR.search(j["title"]) and
                   AUDIT_REL.search(j["title"]+" "+str(j.get("department",""))+" "+str(j.get("team","")))]
        api_match={j["url"] for j in api_raw}
        api_missed=[j for j in api_audit if j["url"] not in api_match]
        audit_unique=api_audit; audit_missed=api_missed
        # Cross-check every candidate against the same ID and title on the
        # direct first-party detail page with an active application control.
        if o["name"]=="Airwallex":
            chosen,deferred=airwallex_validation_queue(api_raw)
            jobs=validate_jobs(chosen,{job_key(j["url"]) for j in api["jobs"]},max_workers=2)+deferred
        else:
            jobs=validate_jobs(api_raw,{job_key(j["url"]) for j in api["jobs"]})

    if embedded:
        evidence.append({"url":embedded["source"],"embedded_complete":embedded["complete"],
                         "official_total":embedded["official_total"],"job_link_count":len(embedded["jobs"]),
                         "listing_like":True,"static_complete_evidence":embedded["complete"],
                         "evidence_kind":embedded["evidence_kind"],"embedded_error":embedded["error"]})
        if embedded["jobs"]:
            st="official_site_scanned"
            coverage="verified_complete" if embedded["complete"] else "partial"
            indexed=embedded["jobs"]
            matched=[j for j in indexed if strategic_inventory_match(j)]
            independent=[j for j in indexed if AUDIT_SENIOR.search(j["title"]) and
                         AUDIT_REL.search(j["title"]+" "+j.get("department","")+" "+j.get("team",""))]
            chosen_urls={j["url"] for j in matched}
            missed=[j for j in independent if j["url"] not in chosen_urls]
            audit_unique=independent;audit_missed=missed
            chosen,deferred=airwallex_validation_queue(matched,capacity=45,priority_count=40)
            jobs=validate_jobs(chosen,{job_key(j["url"]) for j in indexed},max_workers=4)+deferred

    if static and static.get("complete"):
        coverage="verified_complete"; st="official_site_scanned"
        evidence.append({"url":static["source"],"static_board_complete":True,"official_total":static["official_total"],
                         "job_link_count":len(static["jobs"]),"listing_like":True,"static_complete_evidence":True})
        static_raw=[j for j in static["jobs"] if REL.search(j["title"]+" "+j["url"]) and (SENIOR.search(j["title"]) or re.search(r"\\b(mlro|cco|cro|sanctions counsel|regulatory counsel)\\b",j["title"],re.I))]
        static_audit=[j for j in static["jobs"] if AUDIT_REL.search(j["title"]+" "+j["url"]) and AUDIT_SENIOR.search(j["title"])]
        matched={j["url"] for j in static_raw}; missed=[j for j in static_audit if j["url"] not in matched]
        audit_unique=static_audit; audit_missed=missed
        # The exhausted official listing supersedes incidental page candidates.
        jobs=validate_jobs(static_raw,{job_key(j["url"]) for j in static["jobs"]})

    pending=[{"title":j["title"],"url":j["url"],"reason":j.get("validation_reason"),"source_job_id":j.get("source_job_id")}
             for j in jobs if not j.get("apply_live")]
    return {"name":o["name"],"kind":o["kind"],"status":st,"vacancy_coverage":coverage,
            "listing_evidence":evidence,"pending_validation":pending,
            "match_audit":{"candidate_count":len(audit_unique),"matched_count":len(audit_unique)-len(audit_missed),"missed":audit_missed[:20]},
            "checked_at":iso(),"duration_ms":int((time.monotonic()-t)*1000),"routes_tried":tried[-18:],
            "successful_routes":[{"url":f["final"],"method":f["method"],"status":f["status"]} for f in success[:6]],
            "jobs":jobs,"error":None if st!="technical_failure" else "No verifiable official vacancy route completed","_org":o}

def inventory_job_links(html,final,o):
    soup=BeautifulSoup(html,"html.parser"); out={}
    for a in soup.find_all("a",href=True):
        title=a.get_text(" ",strip=True); u=norm(urljoin(final,a["href"]))
        if 4<=len(title)<=180 and u.startswith("http") and allowed(u,o) and JOBURL.search(u):
            if inventory_url(u):
                out[u]=title
    return out

def browser_visible_job_links(pg,o):
    """Collect vacancy links that are actually rendered/visible, excluding stale hidden DOM anchors."""
    try:
        rows=pg.eval_on_selector_all("a[href]", """els => els.filter(e => {
            const r=e.getBoundingClientRect(); const s=getComputedStyle(e);
            return r.width>0 && r.height>0 && s.display!=='none' && s.visibility!=='hidden';
        }).map(e => [e.href, (e.innerText || e.textContent || '').trim()])""")
    except Exception:
        return {}
    out={}
    for href,title in rows:
        u=norm(urljoin(pg.url,href or ""))
        title=(title or "").strip()
        if 4<=len(title)<=180 and u.startswith("http") and allowed(u,o) and JOBURL.search(u) and inventory_url(u):
            out[u]=title
    return out

def locator_all_inner_texts(locator):
    """Playwright Python Locator.all_inner_texts accepts no timeout argument."""
    return locator.all_inner_texts()


def merge_validated_jobs(existing, newly_checked):
    """Merge board recovery without losing an independently verified live job."""
    by_key={job_key(j["url"]):j for j in existing}
    for j in newly_checked:
        key=job_key(j["url"])
        if j.get("apply_live") or not by_key.get(key,{}).get("apply_live"):
            by_key[key]=j
    return list(by_key.values())


def browser_retry(rs):
    """Best-effort deep recovery with hard time budgets; expired checks remain unproven."""
    targets=[r for r in rs if
             (r["status"]=="technical_failure" or r["vacancy_coverage"] in ("partial","unproven"))
             and not (r["name"]=="Airwallex" and
                      any(e.get("api_complete") and "api.ashbyhq.com" in e.get("url","")
                          for e in r.get("listing_evidence",[])))]
    if not targets:return
    targets.sort(key=lambda r:(r["status"]!="technical_failure", r["vacancy_coverage"]!="partial",r["name"]))
    # Direct detail + current official-board proof from the HTTP phase is already
    # valid for that job, even if the entire board cannot be exhaustively enumerated.
    # Never revoke it just because a separate browser coverage audit times out.
    try: from playwright.sync_api import sync_playwright
    except Exception:return
    deadline=time.monotonic()+BROWSER_BUDGET
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); c=b.new_context(user_agent=UA,locale="en-GB")
        for index,r in enumerate(targets):
            if time.monotonic()>=deadline:
                r["browser_recovery_incomplete"]="global_budget_exhausted"
                continue
            started=time.monotonic()
            # Reserve a fair first-pass time slice for every unresolved organisation.
            remaining=len(targets)-index
            fair_share=max(7.0,(deadline-started)/remaining)
            org_deadline=min(deadline,started+min(BROWSER_ORG_BUDGET,fair_share))
            o=r["_org"]; unresolved=r["status"]=="technical_failure"
            likely=sorted(r["listing_evidence"],key=lambda x:(0 if x.get("listing_like") else 1,0 if x.get("job_link_count",0) else 1,-x.get("job_link_count",0)))
            urls=[]
            if likely: urls.extend(x["url"] for x in likely[:3])
            urls.extend(candidates(o)[:3])
            urls=list(dict.fromkeys(urls))
            observed_links={}
            for u in urls:
                if time.monotonic()>=org_deadline:
                    r["browser_recovery_incomplete"]="organisation_budget_exhausted"
                    break
                pg=c.new_page(); t=time.monotonic()
                url_deadline=min(org_deadline,t+BROWSER_URL_BUDGET)
                all_links={}; visited=set(); terminal=False
                try:
                    resp=pg.goto(u,wait_until="domcontentloaded",timeout=12000); pg.wait_for_timeout(450)
                    final=pg.url; sc=resp.status if resp else None
                    if not (sc and sc<400 and allowed(final,o)): continue
                    for page_no in range(12):
                        if time.monotonic()>=url_deadline:break
                        current=pg.url
                        # SPA boards (notably Rabobank) can paginate without changing the URL.
                        # Identify a rendered page by URL + a small stable sample of visible job IDs.
                        page_state=(current,tuple(sorted(browser_visible_job_links(pg,o))[:5]))
                        if page_state in visited and page_no: break
                        visited.add(page_state)
                        stable=0
                        for _ in range(6):
                            if time.monotonic()>=url_deadline:break
                            before=len(all_links)
                            all_links.update(browser_visible_job_links(pg,o))
                            try: pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            except Exception: pass
                            pg.wait_for_timeout(350)
                            clicked=False
                            # One bulk DOM read instead of up to 250 sequential 150ms inner_text calls.
                            loc=pg.locator("button, a")
                            try: labels=locator_all_inner_texts(loc)
                            except Exception: labels=[]
                            for i,label in enumerate(labels[:100]):
                                if DYNAMIC_MORE.search(label or ""):
                                    el=loc.nth(i)
                                    try:
                                        if el.is_visible():
                                            el.click(timeout=900); pg.wait_for_timeout(450); clicked=True; break
                                    except Exception: pass
                            all_links.update(browser_visible_job_links(pg,o))
                            stable=stable+1 if len(all_links)==before and not clicked else 0
                            if stable>=2:break
                        if time.monotonic()>=url_deadline:break
                        html=pg.content(); soup=BeautifulSoup(html,"html.parser")
                        next_url=None
                        nxt=soup.find("a",attrs={"rel":lambda v:v and ("next" in v if isinstance(v,list) else "next" in str(v).lower())})
                        if nxt and nxt.get("href"): next_url=norm(urljoin(pg.url,nxt["href"]))
                        if not next_url:
                            for a in soup.find_all("a",href=True):
                                if re.fullmatch(r"\s*(next|volgende|suivant|weiter|›|»)\s*",a.get_text(" ",strip=True),re.I):
                                    next_url=norm(urljoin(pg.url,a["href"]));break
                        numeric_clicked=False
                        if not next_url:
                            # React/SPA career boards often expose numbered pagination as buttons
                            # rather than hrefs. Click the exact next page number and require the
                            # rendered job identity sample to change on the next iteration.
                            wanted=str(page_no+2)
                            try:
                                buttons=pg.locator("button")
                                labels=locator_all_inner_texts(buttons)
                                for bi,label in enumerate(labels[:80]):
                                    if (label or "").strip()==wanted and buttons.nth(bi).is_visible():
                                        buttons.nth(bi).click(timeout=900)
                                        pg.wait_for_timeout(500)
                                        numeric_clicked=True
                                        break
                            except Exception:
                                numeric_clicked=False
                        if numeric_clicked:
                            continue
                        if not next_url:
                            body=soup.get_text(" ",strip=True)
                            m=re.search(r"Displaying\s+(\d+)\s*-\s*(\d+)\s+of\s+(\d+)",body,re.I)
                            if m and int(m.group(2))<int(m.group(3)):
                                pp=urlparse(pg.url); qs=parse_qs(pp.query); current_page=int((qs.get("page") or ["1"])[0] or 1)
                                qs["page"]=[str(current_page+1)]
                                next_url=urlunparse((pp.scheme,pp.netloc,pp.path,pp.params,urlencode(qs,doseq=True),pp.fragment))
                        if next_url and next_url not in visited and allowed(next_url,o):
                            pg.goto(next_url,wait_until="domcontentloaded",timeout=12000); pg.wait_for_timeout(350);continue
                        terminal=True;break
                    txt=pg.locator("body").inner_text(timeout=3000)
                    html=pg.content(); f2={"ok":True,"url":u,"final":pg.url,"status":sc,"html":html,"text":txt,"method":"browser-exhaustive","error":None,"ms":0}
                    ev=listing_evidence(f2,o);ev["browser_inventory_count"]=len(all_links);ev["browser_pages_traversed"]=len(visited);ev["browser_terminal"]=terminal
                    r["listing_evidence"].append(ev)
                    r["routes_tried"].append({"url":u,"final":pg.url,"method":"browser-exhaustive","status":sc,"ok":True,"error":None,"ms":int((time.monotonic()-t)*1000)})
                    observed_links.update(all_links)
                    if all_links and terminal and ev.get("official_total")==len(all_links):
                        r["vacancy_coverage"]="verified_complete"
                    elif o["no_public_hint"] and terminal and not all_links:
                        r["vacancy_coverage"]="verified_no_public_board"
                    if unresolved and (all_links or (o["no_public_hint"] and terminal and not all_links)):
                        r["status"]="no_public_vacancy_board" if o["no_public_hint"] and not all_links else ("official_ats_scanned" if isats(pg.url) else "official_site_scanned")
                        r["error"]=None
                    r["successful_routes"].append({"url":pg.url,"method":"browser-exhaustive","status":sc})
                    if r["vacancy_coverage"] in ("verified_complete","verified_no_public_board"):break
                except Exception as e:
                    r["routes_tried"].append({"url":u,"final":getattr(pg,"url",u),"method":"browser-exhaustive","status":None,"ok":False,"error":f"{type(e).__name__}: {e}","ms":int((time.monotonic()-t)*1000)})
                finally: pg.close()
            # Validate direct vacancy pages once per organisation, never once per attempted listing URL.
            if observed_links:
                raw=[{"title":title,"url":url} for url,title in observed_links.items() if REL.search(title+" "+url) and (SENIOR.search(title) or re.search(r"\b(mlro|cco|cro|sanctions counsel|regulatory counsel)\b",title,re.I))]
                audit=[{"title":title,"url":url} for url,title in observed_links.items() if AUDIT_REL.search(title+" "+url) and AUDIT_SENIOR.search(title)]
                matched_urls={j["url"] for j in raw}
                missed=[j for j in audit if j["url"] not in matched_urls]
                r["match_audit"]={"candidate_count":len(audit),"matched_count":len(audit)-len(missed),"missed":missed[:20]}
                r["jobs"]=merge_validated_jobs(r.get("jobs",[]),validate_jobs(raw,{job_key(url) for url in observed_links}))
            print(json.dumps({"phase":"browser_recovery","organisation":r["name"],"status":r["status"],"vacancy_coverage":r["vacancy_coverage"],"seconds":round(time.monotonic()-started,1),"remaining_global_seconds":round(deadline-time.monotonic(),1)},ensure_ascii=False),flush=True)
        c.close();b.close()

def qa_snapshot(payload):
    """Fail closed before persisting/alerting when a supposedly live job lacks dual liveness proof."""
    bad=[]
    for r in payload.get("organisations",[]):
        for j in r.get("jobs",[]):
            if j.get("apply_live") and not (j.get("live") and j.get("board_present") and j.get("http_status")==200):
                bad.append({"organisation":r["name"],"title":j.get("title"),"url":j.get("url")})
    for j in payload.get("live_relevant_jobs",[]):
        if not (j.get("apply_live") and j.get("live") and j.get("board_present") and j.get("http_status")==200):
            bad.append({"organisation":j.get("organisation"),"title":j.get("title"),"url":j.get("url")})
    if bad:
        raise RuntimeError(f"live-vacancy QA failed for {len(bad)} record(s): {bad[:5]}")
    return {"passed":True,"rule":"direct_detail_live_plus_current_board_presence","live_jobs_checked":len(payload.get("live_relevant_jobs",[]))}

def main():
    reg=load_registry(); old=set(); latest=DATA/"latest.json"
    if latest.exists():
        try:
            for o in json.loads(latest.read_text())["organisations"]:
                old|={j["url"] for j in o.get("jobs",[]) if j.get("apply_live")}
        except Exception: pass
    started=iso(); scan_started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex: rs=list(ex.map(scan,reg))
    print(json.dumps({"phase":"http_scan_complete","organisations":len(rs),"seconds":round(time.monotonic()-scan_started,1)}),flush=True)
    browser_retry(rs)
    for r in rs:
        evidence=r.get("listing_evidence",[])
        totals=[e.get("official_total") for e in evidence
                if type(e.get("official_total")) is int]
        found=[e.get("browser_inventory_count",0) for e in evidence]
        found += [e.get("job_link_count",0) for e in evidence]
        r["inventory_audit"]={
            "official_total":max(totals) if totals else None,
            "observed_job_links":max(found,default=0),
            "relevant_candidates":len(r.get("jobs",[])),
            "live_apply_verified":sum(bool(j.get("apply_live")) for j in r.get("jobs",[])),
            "coverage":r["vacancy_coverage"],
            "failure":r.get("browser_recovery_incomplete") or r.get("error") or
                       ("inventory_not_proven_exhaustive" if r["vacancy_coverage"] in ("partial","unproven") else None),
            "checked_at":r["checked_at"]
        }
        r.pop("_org",None)
    rs.sort(key=lambda x:(x["kind"],x["name"].lower()))
    ks=("official_site_scanned","official_ats_scanned","no_public_vacancy_board","technical_failure")
    counts={k:sum(r["status"]==k for r in rs) for k in ks}
    bykind={kind:{k:sum(r["kind"]==kind and r["status"]==k for r in rs) for k in ks} for kind in ("recruiter","employer")}
    jobs=[]
    for r in rs:
        for j in r["jobs"]:
            if j.get("apply_live"): jobs.append({**j,"organisation":r["name"],"kind":r["kind"],"is_new":j["url"] not in old})
    ok=len(reg)-counts["technical_failure"]
    coverage_counts={k:sum(r["vacancy_coverage"]==k for r in rs) for k in ("verified_complete","verified_no_public_board","partial","unproven")}
    excluded={"DB Contractors UK","Risk Talent Associates"}
    target=[r for r in rs if r["name"] not in excluded]
    proven=[r for r in target if r["vacancy_coverage"] in ("verified_complete","verified_no_public_board")]
    vacancy_percent=round(100*len(proven)/len(target),1)
    audit_scope=[r for r in target if r["vacancy_coverage"]=="verified_complete"]
    audit_total=sum(r.get("match_audit",{}).get("candidate_count",0) for r in audit_scope)
    audit_matched=sum(r.get("match_audit",{}).get("matched_count",0) for r in audit_scope)
    match_recall=round(100*audit_matched/audit_total,1) if audit_total else None
    payload={"schema_version":4,"run_date":nldate(),"started_at":started,"completed_at":iso(),"total_expected":len(reg),"total_classified":len(rs),"complete":len(rs)==len(reg),"coverage_percent":round(100*len(rs)/len(reg),1),"successful_control_count":ok,"successful_control_percent":round(100*ok/len(reg),1),"vacancy_coverage_counts":coverage_counts,"match_audit":{"candidate_count":audit_total,"matched_count":audit_matched,"recall_percent":match_recall},"counts":counts,"counts_by_kind":bykind,"technical_failures":[{"name":r["name"],"kind":r["kind"],"error":r["error"],"routes_tried":r["routes_tried"]} for r in rs if r["status"]=="technical_failure"],"live_relevant_jobs":jobs,"organisations":rs}
    payload["qa"]=qa_snapshot(payload)
    text=json.dumps(payload,ensure_ascii=False,indent=2); latest.write_text(text); (DATA/f'{payload["run_date"]}.json').write_text(text)
    incomplete=[{"name":r["name"],"kind":r["kind"],"coverage":r["vacancy_coverage"],"status":r["status"]} for r in target if r["vacancy_coverage"] not in ("verified_complete","verified_no_public_board")]
    missed_examples=[]
    for rr in audit_scope:
        for jj in rr.get("match_audit",{}).get("missed",[]):
            missed_examples.append({"organisation":rr["name"],"title":jj["title"],"url":jj["url"]})
    summary={"run_date":payload["run_date"],"target_expected":len(target),"target_proven":len(proven),"vacancy_coverage_percent":vacancy_percent,
             "match_audit":{"candidate_count":audit_total,"matched_count":audit_matched,"recall_percent":match_recall,
                            "missed_count":audit_total-audit_matched,"missed_examples":missed_examples[:100]},
             "incomplete":incomplete,"technical_failures":[x["name"] for x in payload["technical_failures"]]}
    (DATA/"coverage-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({"complete":payload["complete"],"coverage":payload["coverage_percent"],"successful_control":payload["successful_control_percent"],
                      "vacancy_coverage_percent":vacancy_percent,"match_recall_percent":match_recall,"incomplete_names":[x["name"] for x in incomplete],
                      "counts":counts,"live_relevant_jobs":len(jobs),"technical_failure_names":[x["name"] for x in payload["technical_failures"]]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
