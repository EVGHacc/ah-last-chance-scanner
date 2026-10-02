#!/usr/bin/env python3
"""Strict first-party Rabobank inventory probe.

Completeness is true only when stable Rabobank requisition IDs extracted from
rabobank.jobs exactly reconcile to the official total printed by the listing.
"""
import json, re, sys
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

LISTING="https://rabobank.jobs/nl/vacatures/"
TOTAL_RE=re.compile(r"\b([0-9]{1,5})\s+(?:vacatures?|jobs?)\b",re.I)
REQ_RE=re.compile(r"\bJR_[0-9]{6,}\b",re.I)

def parse_inventory(html, base=LISTING):
    soup=BeautifulSoup(html,"html.parser")
    text=soup.get_text(" ",strip=True)
    totals=[int(m.group(1)) for m in TOTAL_RE.finditer(text)]
    official_total=max(totals) if totals else None
    jobs={}
    for a in soup.find_all("a",href=True):
        u=urljoin(base,a["href"])
        if urlparse(u).hostname!="rabobank.jobs":
            continue
        m=REQ_RE.search(u)
        if not m:
            continue
        ident=m.group(0).upper()
        jobs[ident]={"id":ident,"url":u,"title":a.get_text(" ",strip=True)}
    return {
        "official_total":official_total,
        "unique_count":len(jobs),
        "complete":bool(official_total is not None and official_total>0 and len(jobs)==official_total),
        "jobs":list(jobs.values()),
    }

def probe(url=LISTING, timeout=30):
    r=requests.get(url,headers={"User-Agent":"Mozilla/5.0 VacancyMonitor/2"},timeout=timeout)
    r.raise_for_status()
    if urlparse(r.url).hostname!="rabobank.jobs":
        raise RuntimeError("Rabobank listing redirected off first-party domain")
    out=parse_inventory(r.text,r.url)
    out.update({"source":r.url,"http_status":r.status_code})
    return out

if __name__=="__main__":
    result=probe()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(0 if result["complete"] else 2)
