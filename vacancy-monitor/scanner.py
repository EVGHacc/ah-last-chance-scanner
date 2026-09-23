#!/usr/bin/env python3
import csv, json, os, re, time, concurrent.futures
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote_plus, parse_qs, unquote
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
REL=re.compile(r"(compliance|risk|audit|aml|financial.?crime|sanction|governance|regulatory|controls?|assurance|\bmlro\b|\bcco\b|\bcro\b|responsible.?ai|trust.?safety|resilien|business.?control|integrity|fraud|financieel.?economische.?criminaliteit|witwassen)",re.I)
JOBURL=re.compile(r"(/job(?:s)?/|/vacanc|/position|/career|/opportunit|job[_-]|vacature|search-jobs|/offre-de-emploi/|/stellenangebot/)",re.I)
SENIOR=re.compile(r"(head|director|executive.?director|senior.?manager|lead|chief|vice.?president|\bvp\b|principal|partner|manager|hoofd|directeur|global|regional|strateg|expert)",re.I)
APPLY=re.compile(r"(apply.?now|\bapply\b|solliciteer|submit.?application|start.?application)",re.I)
PAGING=re.compile(r"(next|volgende|suivant|weiter|load more|toon meer|show more|page [2-9])",re.I)
CLOSED=re.compile(r"(no.?longer.?available|position.?has.?been.?filled|vacature.?is.?gesloten|job.?is.?closed|applications?.?closed|expired)",re.I)
COMMON=("/careers","/jobs","/vacatures","/job-search","/open-roles","/positions")

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

def listing_evidence(f,o):
    """Evidence of a populated listing, never a claim that its inventory is complete."""
    s=BeautifulSoup(f["html"],"html.parser")
    links=[]
    for a in s.find_all("a",href=True):
        u=norm(urljoin(f["final"],a["href"]))
        title=a.get_text(" ",strip=True)
        if 4<=len(title)<=180 and allowed(u,o) and JOBURL.search(u) and not PAGING.search(title):
            if not re.search(r"(search|filter|login|privacy|cookie|alert|subscribe|blog|article)",u,re.I):
                links.append(u)
    pagination=bool(s.find(attrs={"rel":"next"}) or any(PAGING.search(a.get_text(" ",strip=True)) for a in s.find_all("a",href=True)))
    return {"url":f["final"],"job_link_count":len(set(links)),"pagination_seen":pagination}

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

def validate_jobs(js):
    out=[]
    for j in js[:50]:
        f=fetch(j["url"],"job-live-check"); text=f["text"]
        live=f["ok"] and (j["title"].lower()[:24] in text.lower() or len(j["title"])<12)
        j.update({"url":f["final"],"live":live,"apply_live":bool(live and APPLY.search(text) and not CLOSED.search(text)),"http_status":f["status"],"checked_at":iso()}); out.append(j)
    return out

def scan(o):
    t=time.monotonic(); tried=[]; success=[]; q=candidates(o); seen=set()
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
    jobs=validate_jobs(list({(j["title"].lower(),j["url"]):j for j in js}.values()))
    evidence=[listing_evidence(f,o) for f in success]
    if success:
        if o["no_public_hint"] and not jobs: st="no_public_vacancy_board"
        elif any(isats(f["final"]) for f in success): st="official_ats_scanned"
        elif any(CAREER.search(f["final"]+" "+f["text"][:12000]) for f in success): st="official_site_scanned"
        else: st="no_public_vacancy_board" if o["no_public_hint"] else "technical_failure"
    else: st="technical_failure"
    # A 200 response, a careers landing page, and a manually tagged lack of a board
    # cannot establish complete vacancy coverage.  Keep this separate from reachability.
    listing=[e for e in evidence if e["job_link_count"]]
    coverage="partial" if listing else ("not_applicable_unverified" if o["no_public_hint"] else "unproven")
    return {"name":o["name"],"kind":o["kind"],"status":st,"vacancy_coverage":coverage,"listing_evidence":evidence,"checked_at":iso(),"duration_ms":int((time.monotonic()-t)*1000),"routes_tried":tried[-18:],"successful_routes":[{"url":f["final"],"method":f["method"],"status":f["status"]} for f in success[:6]],"jobs":jobs,"error":None if st!="technical_failure" else "No verifiable official vacancy route completed","_org":o}

def browser_retry(rs):
    bad=[r for r in rs if r["status"]=="technical_failure" or r["vacancy_coverage"]=="unproven"]
    if not bad:return
    try: from playwright.sync_api import sync_playwright
    except Exception:return
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True); c=b.new_context(user_agent=UA,locale="en-GB")
        for r in bad:
            o=r["_org"]
            unresolved=r["status"]=="technical_failure"
            # Dynamic listings are common. Render the best available listing once,
            # without spending the whole run opening generic corporate pages.
            likely=sorted(r["listing_evidence"],key=lambda x:(0 if re.search(r"(search-results|listing-page|/vacatures|/jobs|openings)",x["url"],re.I) else 1,-x["job_link_count"]))
            urls=candidates(o)[:4] if unresolved else [likely[0]["url"] if likely else o["seed_urls"][0]]
            for u in urls:
                pg=c.new_page(); t=time.monotonic()
                try:
                    resp=pg.goto(u,wait_until="domcontentloaded",timeout=10000); pg.wait_for_timeout(1200)
                    txt=pg.locator("body").inner_text(timeout=3000); final=pg.url; sc=resp.status if resp else None
                    ok=bool(sc and sc<400 and len(txt)>300 and allowed(final,o))
                    r["routes_tried"].append({"url":u,"final":final,"method":"browser","status":sc,"ok":ok,"error":None if ok else "browser route unusable","ms":int((time.monotonic()-t)*1000)})
                    if ok:
                        html=pg.content(); f={"ok":True,"url":u,"final":final,"status":sc,"html":html,"text":txt,"method":"browser","error":None,"ms":0}
                        fresh=extract_jobs(f,o)
                        if fresh: r["jobs"]=validate_jobs(fresh)
                        r["listing_evidence"].append(listing_evidence(f,o))
                        if any(e["job_link_count"] for e in r["listing_evidence"]): r["vacancy_coverage"]="partial"
                        if unresolved:
                            r["status"]="no_public_vacancy_board" if o["no_public_hint"] and not r["jobs"] else ("official_ats_scanned" if isats(final) else "official_site_scanned")
                            r["error"]=None
                        r["successful_routes"].append({"url":final,"method":"browser","status":sc}); break
                except Exception as e:
                    r["routes_tried"].append({"url":u,"final":u,"method":"browser","status":None,"ok":False,"error":f"{type(e).__name__}: {e}","ms":int((time.monotonic()-t)*1000)})
                finally: pg.close()
        c.close(); b.close()

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
    coverage_counts={k:sum(r["vacancy_coverage"]==k for r in rs) for k in ("verified_complete","partial","unproven","not_applicable_unverified")}
    payload={"schema_version":2,"run_date":nldate(),"started_at":started,"completed_at":iso(),"total_expected":105,"total_classified":len(rs),"complete":len(rs)==105,"coverage_percent":round(100*len(rs)/105,1),"successful_control_count":ok,"successful_control_percent":round(100*ok/105,1),"vacancy_coverage_counts":coverage_counts,"counts":counts,"counts_by_kind":bykind,"technical_failures":[{"name":r["name"],"kind":r["kind"],"error":r["error"],"routes_tried":r["routes_tried"]} for r in rs if r["status"]=="technical_failure"],"live_relevant_jobs":jobs,"organisations":rs}
    text=json.dumps(payload,ensure_ascii=False,indent=2); latest.write_text(text); (DATA/f'{payload["run_date"]}.json').write_text(text)
    print(json.dumps({"complete":payload["complete"],"coverage":payload["coverage_percent"],"successful_control":payload["successful_control_percent"],"counts":counts,"live_relevant_jobs":len(jobs),"technical_failure_names":[x["name"] for x in payload["technical_failures"]]},ensure_ascii=False,indent=2))

if __name__=="__main__": main()
