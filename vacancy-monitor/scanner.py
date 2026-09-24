#!/usr/bin/env python3
import csv, json, os, re, time, concurrent.futures
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus, parse_qs, unquote, urlencode, urlunparse
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"; DATA.mkdir(exist_ok=True)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36 VacancyMonitor/1.0"
H={"User-Agent":UA,"Accept-Language":"en-GB,en;q=0.9,nl;q=0.8"}
TIMEOUT=int(os.getenv("VACANCY_TIMEOUT","12")); WORKERS=int(os.getenv("VACANCY_WORKERS","12"))
ATS=("myworkdayjobs.com","workday.com","oraclecloud.com","greenhouse.io","lever.co","teamtailor.com","recruitee.com","ashbyhq.com","breezy.hr","smartrecruiters.com","successfactors.com","eightfold.ai","icims.com")
CAREER=re.compile(r"(job|career|vacanc|position|opportunit|werken.?bij|open.?roles)",re.I)
REL=re.compile(r"(compliance|risk|audit|anti.?money|aml|financial.?crime|sanction|governance|regulat|controls?|assurance|oversight|mlro|cco|cro|responsible.?ai|trust.?safety|resilien|continuity|business.?control|integrity|fraud|investigation|financial.?intelligence|conduct|ethics|remediation|non.?financial|financieel.?economische.?criminaliteit|witwassen)",re.I)
JOBURL=re.compile(r"(/job(?:s)?/|/vacanc|/position|/career|/opportunit|job[_-]|vacature|search-jobs|/offre-de-emploi/|/stellenangebot/)",re.I)
AUDIT_REL=re.compile(r"(compliance|risk|audit|anti.?money|aml|financial.?crime|sanction|governance|regulat|control|assurance|oversight|resilien|continuity|integrity|fraud|investigation|financial.?intelligence|conduct|ethics|responsible.?ai|trust.?safety|remediation|non.?financial)",re.I)
AUDIT_SENIOR=re.compile(r"(head|director|senior|lead|chief|vice.?president|\\bvp\\b|principal|partner|manager|expert|global|regional|\\bmlro\\b|\\bcco\\b|\\bcro\\b)",re.I)
SENIOR=re.compile(r"(head|director|executive.?director|senior|lead|chief|vice.?president|vp|principal|partner|manager|hoofd|directeur|global|regional|strateg|expert|business.?resilien.?officer|operational.?continuity)",re.I)
APPLY=re.compile(r"(apply.?now|\bapply\b|solliciteer|submit.?application|start.?application)",re.I)
PAGING=re.compile(r"(next|volgende|suivant|weiter|load more|toon meer|show more|page [2-9])",re.I)
DYNAMIC_MORE=re.compile(r"(load more|toon meer|show more|view more|see more|meer vacatures|more jobs)",re.I)
LISTING_URL=re.compile(r"(/jobs?/?$|/vacatures/?$|job-search|search-jobs|search-results|/positions/?$|open-roles|open-jobs|careers/search|offre-de-emploi/liste)",re.I)
CLOSED=re.compile(r"(no.?longer.?available|position.?has.?been.?filled|vacature.?is.?gesloten|job.?is.?closed|applications?.?closed|expired)",re.I)
COMMON=("/careers","/jobs","/vacatures","/job-search","/open-roles","/positions")
API_BOARDS={
    "Lloyds Banking Group":{"type":"workday","url":"https://lbg.wd3.myworkdayjobs.com/wday/cxs/lbg/LBG_Careers/jobs","board":"https://lbg.wd3.myworkdayjobs.com/LBG_Careers"},
    "Visa":{"type":"workday","url":"https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/Visa/jobs","board":"https://visa.wd5.myworkdayjobs.com/Visa"},
    "Zerohash":{"type":"breezy","url":"https://zero-hash.breezy.hr/json","board":"https://zero-hash.breezy.hr"}
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
    if len(out)!=105: raise RuntimeError(f"registry count {len(out)} != 105")
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

def api_inventory(o):
    """Enumerate selected public ATS feeds and prove completeness against their own totals."""
    c=API_BOARDS.get(o["name"])
    if not c: return None
    try:
        if c["type"]=="workday":
            first=requests.post(c["url"],headers=H,json={"limit":20,"offset":0,"searchText":"","appliedFacets":{}},timeout=TIMEOUT)
            first.raise_for_status(); d=first.json(); total=int(d.get("total",0)); batches=[d]
            for offset in range(20,total,20):
                rr=requests.post(c["url"],headers=H,json={"limit":20,"offset":offset,"searchText":"","appliedFacets":{}},timeout=TIMEOUT)
                rr.raise_for_status(); batches.append(rr.json())
            items=[]
            for b in batches:
                for j in b.get("jobPostings",[]):
                    path=j.get("externalPath") or ""
                    title=j.get("title") or ""
                    if path and title:
                        items.append({"title":title,"url":c["board"].rstrip("/")+path})
            uniq={j["url"]:j for j in items}
            return {"complete":bool(total and len(uniq)==total),"official_total":total,"jobs":list(uniq.values()),"source":c["url"],"error":None}
        if c["type"]=="breezy":
            rr=requests.get(c["url"],headers=H,timeout=TIMEOUT); rr.raise_for_status(); d=rr.json()
            if not isinstance(d,list): raise ValueError("Expected Breezy positions list")
            items=[]
            for j in d:
                title=j.get("name") or j.get("title") or ""; u=j.get("url") or ""
                if title and u: items.append({"title":title,"url":u})
            uniq={j["url"]:j for j in items}
            return {"complete":len(uniq)==len(d),"official_total":len(d),"jobs":list(uniq.values()),"source":c["url"],"error":None}
    except Exception as e:
        return {"complete":False,"official_total":None,"jobs":[],"source":c["url"],"error":f"{type(e).__name__}: {e}"}
    return None

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

def validate_jobs(js,board_keys=None):
    board_keys=set(board_keys or ())
    out=[]
    for j in js[:50]:
        requested=j["url"]; f=fetch(requested,"job-live-check"); text=f["text"]
        direct_live=f["ok"] and (j["title"].lower()[:24] in text.lower() or len(j["title"])<12)
        board_present=job_key(requested) in board_keys or job_key(f["final"]) in board_keys
        apply_live=bool(direct_live and board_present and APPLY.search(text) and not CLOSED.search(text))
        if apply_live: reason="direct_live_and_current_board"
        elif not board_present: reason="not_on_current_board"
        elif not direct_live: reason="detail_page_not_live"
        elif CLOSED.search(text): reason="closed_marker"
        else: reason="no_live_apply_control"
        j.update({"url":f["final"],"live":direct_live,"board_present":board_present,"apply_live":apply_live,
                  "validation_reason":reason,"http_status":f["status"],"checked_at":iso()}); out.append(j)
    return out

def scan(o):
    t=time.monotonic(); tried=[]; success=[]; q=candidates(o); seen=set()
    api=api_inventory(o); static=static_inventory(o)
    while q and len(seen)<24:
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
    if api and api.get("complete"):
        coverage="verified_complete"; st="official_ats_scanned"
        evidence.append({"url":api["source"],"api_complete":True,"official_total":api["official_total"],"job_link_count":len(api["jobs"]),"listing_like":True,"static_complete_evidence":True})
        api_raw=[j for j in api["jobs"] if REL.search(j["title"]+" "+j["url"]) and (SENIOR.search(j["title"]) or re.search(r"\\b(mlro|cco|cro|sanctions counsel|regulatory counsel)\\b",j["title"],re.I))]
        api_audit=[j for j in api["jobs"] if AUDIT_REL.search(j["title"]+" "+j["url"]) and AUDIT_SENIOR.search(j["title"])]
        api_match={j["url"] for j in api_raw}
        api_missed=[j for j in api_audit if j["url"] not in api_match]
        audit_unique=api_audit; audit_missed=api_missed
        if api_raw: jobs=validate_jobs(api_raw,{job_key(j["url"]) for j in api["jobs"]})

    if static and static.get("complete"):
        coverage="verified_complete"; st="official_site_scanned"
        evidence.append({"url":static["source"],"static_board_complete":True,"official_total":static["official_total"],
                         "job_link_count":len(static["jobs"]),"listing_like":True,"static_complete_evidence":True})
        static_raw=[j for j in static["jobs"] if REL.search(j["title"]+" "+j["url"]) and (SENIOR.search(j["title"]) or re.search(r"\\b(mlro|cco|cro|sanctions counsel|regulatory counsel)\\b",j["title"],re.I))]
        static_audit=[j for j in static["jobs"] if AUDIT_REL.search(j["title"]+" "+j["url"]) and AUDIT_SENIOR.search(j["title"])]
        matched={j["url"] for j in static_raw}; missed=[j for j in static_audit if j["url"] not in matched]
        audit_unique=static_audit; audit_missed=missed
        if static_raw: jobs=validate_jobs(static_raw,{job_key(j["url"]) for j in static["jobs"]})

    return {"name":o["name"],"kind":o["kind"],"status":st,"vacancy_coverage":coverage,
            "listing_evidence":evidence,
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

def browser_retry(rs):
    """Render incomplete boards and exhaust scrolling/load-more/next pagination."""
    targets=[r for r in rs if r["status"]=="technical_failure" or r["vacancy_coverage"] in ("partial","unproven")]
    if not targets:return
    try: from playwright.sync_api import sync_playwright
    except Exception:return
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); c=b.new_context(user_agent=UA,locale="en-GB")
        for r in targets:
            o=r["_org"]; unresolved=r["status"]=="technical_failure"
            likely=sorted(r["listing_evidence"],key=lambda x:(0 if x.get("listing_like") else 1,0 if x.get("job_link_count",0) else 1,-x.get("job_link_count",0)))
            urls=[]
            if likely: urls.extend(x["url"] for x in likely[:3])
            urls.extend(candidates(o)[:3])
            urls=list(dict.fromkeys(urls))
            for u in urls:
                pg=c.new_page(); t=time.monotonic(); all_links={}; visited=set(); terminal=False
                try:
                    resp=pg.goto(u,wait_until="domcontentloaded",timeout=12000); pg.wait_for_timeout(700)
                    final=pg.url; sc=resp.status if resp else None
                    if not (sc and sc<400 and allowed(final,o)): continue
                    for page_no in range(35):
                        current=pg.url
                        if current in visited and page_no: break
                        visited.add(current)
                        stable=0
                        for _ in range(10):
                            html=pg.content(); before=len(all_links)
                            all_links.update(inventory_job_links(html,pg.url,o))
                            # Infinite-scroll boards often need several bottom hits.
                            try: pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            except Exception: pass
                            pg.wait_for_timeout(450)
                            # Click one visible load-more control if present.
                            clicked=False
                            loc=pg.locator("button, a")
                            for i in range(min(loc.count(),250)):
                                el=loc.nth(i)
                                try:
                                    label=(el.inner_text(timeout=150) or "").strip()
                                    if DYNAMIC_MORE.search(label) and el.is_visible():
                                        el.click(timeout=1200); pg.wait_for_timeout(650); clicked=True; break
                                except Exception: pass
                            html=pg.content(); all_links.update(inventory_job_links(html,pg.url,o))
                            stable = stable+1 if len(all_links)==before and not clicked else 0
                            if stable>=2: break
                        html=pg.content(); soup=BeautifulSoup(html,"html.parser")
                        next_url=None
                        nxt=soup.find("a",attrs={"rel":lambda v:v and ("next" in v if isinstance(v,list) else "next" in str(v).lower())})
                        if nxt and nxt.get("href"): next_url=norm(urljoin(pg.url,nxt["href"]))
                        if not next_url:
                            for a in soup.find_all("a",href=True):
                                if re.fullmatch(r"\\s*(next|volgende|suivant|weiter|›|»)\\s*",a.get_text(" ",strip=True),re.I):
                                    next_url=norm(urljoin(pg.url,a["href"])); break
                        if not next_url:
                            body=soup.get_text(" ",strip=True)
                            m=re.search(r"Displaying\\s+(\\d+)\\s*-\\s*(\\d+)\\s+of\\s+(\\d+)",body,re.I)
                            if m and int(m.group(2)) < int(m.group(3)):
                                pp=urlparse(pg.url); qs=parse_qs(pp.query); current_page=int((qs.get("page") or ["1"])[0] or 1)
                                qs["page"]=[str(current_page+1)]
                                next_url=urlunparse((pp.scheme,pp.netloc,pp.path,pp.params,urlencode(qs,doseq=True),pp.fragment))
                        if next_url and next_url not in visited and allowed(next_url,o):
                            pg.goto(next_url,wait_until="domcontentloaded",timeout=12000); pg.wait_for_timeout(500); continue
                        # No forward pagination left and scrolling/load-more stabilized.
                        terminal=True; break
                    txt=pg.locator("body").inner_text(timeout=3000)
                    html=pg.content(); f2={"ok":True,"url":u,"final":pg.url,"status":sc,"html":html,"text":txt,"method":"browser-exhaustive","error":None,"ms":0}
                    ev=listing_evidence(f2,o); ev["browser_inventory_count"]=len(all_links); ev["browser_pages_traversed"]=len(visited); ev["browser_terminal"]=terminal
                    r["listing_evidence"].append(ev)
                    r["routes_tried"].append({"url":u,"final":pg.url,"method":"browser-exhaustive","status":sc,"ok":True,"error":None,"ms":int((time.monotonic()-t)*1000)})
                    # For incomplete/dynamic boards the rendered browser inventory is authoritative
                    # for liveness even when we cannot prove that the whole inventory is exhaustive.
                    if all_links:
                        raw=[{"title":title,"url":url} for url,title in all_links.items() if REL.search(title+" "+url) and (SENIOR.search(title) or re.search(r"\\b(mlro|cco|cro|sanctions counsel|regulatory counsel)\\b",title,re.I))]
                        audit=[{"title":title,"url":url} for url,title in all_links.items() if AUDIT_REL.search(title+" "+url) and AUDIT_SENIOR.search(title)]
                        matched_urls={j["url"] for j in raw}
                        missed=[j for j in audit if j["url"] not in matched_urls]
                        r["match_audit"]={"candidate_count":len(audit),"matched_count":len(audit)-len(missed),"missed":missed[:20]}
                        r["jobs"]=validate_jobs(raw,{job_key(url) for url in all_links})
                    if all_links and terminal and ev.get("official_total") == len(all_links):
                        r["vacancy_coverage"]="verified_complete"
                    elif o["no_public_hint"] and terminal and not all_links:
                        r["vacancy_coverage"]="verified_no_public_board"
                    if unresolved:
                        r["status"]="no_public_vacancy_board" if o["no_public_hint"] and not all_links else ("official_ats_scanned" if isats(pg.url) else "official_site_scanned")
                        if r["status"]!="technical_failure":r["error"]=None
                    r["successful_routes"].append({"url":pg.url,"method":"browser-exhaustive","status":sc})
                    if r["vacancy_coverage"] in ("verified_complete","verified_no_public_board"): break
                except Exception as e:
                    r["routes_tried"].append({"url":u,"final":getattr(pg,"url",u),"method":"browser-exhaustive","status":None,"ok":False,"error":f"{type(e).__name__}: {e}","ms":int((time.monotonic()-t)*1000)})
                finally: pg.close()
        c.close(); b.close()

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
    started=iso()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex: rs=list(ex.map(scan,reg))
    browser_retry(rs)
    for r in rs:r.pop("_org",None)
    rs.sort(key=lambda x:(x["kind"],x["name"].lower()))
    ks=("official_site_scanned","official_ats_scanned","no_public_vacancy_board","technical_failure")
    counts={k:sum(r["status"]==k for r in rs) for k in ks}
    bykind={kind:{k:sum(r["kind"]==kind and r["status"]==k for r in rs) for k in ks} for kind in ("recruiter","employer")}
    jobs=[]
    for r in rs:
        for j in r["jobs"]:
            if j.get("apply_live"): jobs.append({**j,"organisation":r["name"],"kind":r["kind"],"is_new":j["url"] not in old})
    ok=105-counts["technical_failure"]
    coverage_counts={k:sum(r["vacancy_coverage"]==k for r in rs) for k in ("verified_complete","verified_no_public_board","partial","unproven")}
    excluded={"DB Contractors UK","Risk Talent Associates"}
    target=[r for r in rs if r["name"] not in excluded]
    proven=[r for r in target if r["vacancy_coverage"] in ("verified_complete","verified_no_public_board")]
    vacancy_percent=round(100*len(proven)/len(target),1)
    audit_scope=[r for r in target if r["vacancy_coverage"]=="verified_complete"]
    audit_total=sum(r.get("match_audit",{}).get("candidate_count",0) for r in audit_scope)
    audit_matched=sum(r.get("match_audit",{}).get("matched_count",0) for r in audit_scope)
    match_recall=round(100*audit_matched/audit_total,1) if audit_total else None
    payload={"schema_version":4,"run_date":nldate(),"started_at":started,"completed_at":iso(),"total_expected":105,"total_classified":len(rs),"complete":len(rs)==105,"coverage_percent":round(100*len(rs)/105,1),"successful_control_count":ok,"successful_control_percent":round(100*ok/105,1),"vacancy_coverage_counts":coverage_counts,"match_audit":{"candidate_count":audit_total,"matched_count":audit_matched,"recall_percent":match_recall},"counts":counts,"counts_by_kind":bykind,"technical_failures":[{"name":r["name"],"kind":r["kind"],"error":r["error"],"routes_tried":r["routes_tried"]} for r in rs if r["status"]=="technical_failure"],"live_relevant_jobs":jobs,"organisations":rs}
    payload["qa"]=qa_snapshot(payload)
    text=json.dumps(payload,ensure_ascii=False,indent=2); latest.write_text(text); (DATA/f'{payload["run_date"]}.json').write_text(text)
    incomplete=[{"name":r["name"],"kind":r["kind"],"coverage":r["vacancy_coverage"],"status":r["status"]} for r in target if r["vacancy_coverage"] not in ("verified_complete","verified_no_public_board")]
    missed_examples=[]
    for rr in audit_scope:
        for jj in rr.get("match_audit",{}).get("missed",[]):
            missed_examples.append({"organisation":rr["name"],"title":jj["title"],"url":jj["url"]})
    summary={"run_date":payload["run_date"],"target_expected":103,"target_proven":len(proven),"vacancy_coverage_percent":vacancy_percent,
             "match_audit":{"candidate_count":audit_total,"matched_count":audit_matched,"recall_percent":match_recall,
                            "missed_count":audit_total-audit_matched,"missed_examples":missed_examples[:100]},
             "incomplete":incomplete,"technical_failures":[x["name"] for x in payload["technical_failures"]]}
    (DATA/"coverage-summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({"complete":payload["complete"],"coverage":payload["coverage_percent"],"successful_control":payload["successful_control_percent"],
                      "vacancy_coverage_percent":vacancy_percent,"match_recall_percent":match_recall,"incomplete_names":[x["name"] for x in incomplete],
                      "counts":counts,"live_relevant_jobs":len(jobs),"technical_failure_names":[x["name"] for x in payload["technical_failures"]]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
