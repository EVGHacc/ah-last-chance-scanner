import json
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

BASE="https://www.auditcarriere.nl"

class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self._href=None; self._text=[]; self.title=[]; self._in_title=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="a":
            href=a.get("href","")
            if href.startswith("/vacature/") or href.startswith(BASE+"/vacature/"):
                self._href=href; self._text=[]
        if tag=="title": self._in_title=True
    def handle_endtag(self,tag):
        if tag=="a" and self._href:
            title=" ".join(" ".join(self._text).split()); self.links.append((self._href,title)); self._href=None; self._text=[]
        if tag=="title": self._in_title=False
    def handle_data(self,data):
        if self._href: self._text.append(data)
        if self._in_title: self.title.append(data)

class _DetailParser(HTMLParser):
    def __init__(self):
        super().__init__(); self._json=False; self._buf=[]; self.jsonld=[]; self.meta={}; self.h1=[]; self._h1=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=="script" and "application/ld+json" in a.get("type","").lower(): self._json=True; self._buf=[]
        if tag=="meta":
            key=(a.get("property") or a.get("name") or "").lower(); value=a.get("content","").strip()
            if key and value: self.meta[key]=value
        if tag=="h1": self._h1=True
    def handle_endtag(self,tag):
        if tag=="script" and self._json:
            raw="".join(self._buf).strip()
            if raw:
                try:self.jsonld.append(json.loads(raw))
                except Exception:pass
            self._json=False; self._buf=[]
        if tag=="h1": self._h1=False
    def handle_data(self,data):
        if self._json:self._buf.append(data)
        if self._h1:self.h1.append(data)

def _walk(obj):
    if isinstance(obj,list):
        for x in obj: yield from _walk(x)
    elif isinstance(obj,dict):
        yield obj
        for v in obj.values():
            if isinstance(v,(dict,list)): yield from _walk(v)

def _text(value):
    if not isinstance(value,str): return ""
    return " ".join(unescape(re.sub(r"<[^>]+>"," ",value)).split())

def _location(posting):
    loc=posting.get("jobLocation")
    if isinstance(loc,list): loc=loc[0] if loc else {}
    if not isinstance(loc,dict): return ""
    addr=loc.get("address",{})
    if not isinstance(addr,dict): return ""
    return ", ".join(str(addr.get(k)).strip() for k in ("addressLocality","addressRegion","addressCountry") if addr.get(k))

def parse_listing(html):
    p=_PageParser(); p.feed(html)
    hay=" ".join(p.title)+" "+re.sub(r"<[^>]+>"," ",html[:20000])
    m=re.search(r"\b(\d{1,4})\s+vacatures\b",unescape(hay),re.I)
    total=int(m.group(1)) if m else None
    seen=set(); links=[]
    for href,title in p.links:
        url=urljoin(BASE,href); path=urlparse(url).path
        if path in seen: continue
        seen.add(path); links.append((url,title))
    return total,links

def parse_detail(url,html,fallback_title=""):
    p=_DetailParser(); p.feed(html); posting=None
    for root in p.jsonld:
        for obj in _walk(root):
            t=obj.get("@type"); types=t if isinstance(t,list) else [t]
            if any(str(x).casefold()=="jobposting" for x in types): posting=obj; break
        if posting: break
    posting=posting or {}
    title=_text(posting.get("title")) or _text(p.meta.get("og:title")) or _text(" ".join(p.h1)) or _text(fallback_title)
    desc=_text(posting.get("description")) or _text(p.meta.get("description")) or title
    summary=desc[:1200].strip()
    if not title or not summary: raise ValueError("detail missing title/summary")
    org=posting.get("hiringOrganization",{}); employer=_text(org.get("name")) if isinstance(org,dict) else ""
    path=urlparse(url).path.rstrip("/"); job_id=path.split("/")[-1]
    if not job_id: raise ValueError("detail missing stable job id")
    canonical=posting.get("url") if isinstance(posting.get("url"),str) and posting.get("url").startswith("http") else url
    return {"job_id":job_id,"title":title,"short_summary":summary,"job_url":url,"apply_url":canonical,"location":_location(posting),"employer":employer,"published_at":posting.get("datePosted") if isinstance(posting.get("datePosted"),str) else None,"updated_at":posting.get("dateModified") if isinstance(posting.get("dateModified"),str) else None}

@dataclass(frozen=True)
class Inventory:
    jobs: tuple
    authoritative_total: int

def inventory(listing_url_template,fetcher,max_pages=100):
    expected=None; links={}; page=1
    while page<=max_pages:
        html=fetcher(listing_url_template.format(page=page)); total,rows=parse_listing(html)
        if total is None: raise ValueError("visible vacancy total absent")
        if expected is None: expected=total
        elif total!=expected: raise ValueError("vacancy total drift during pagination")
        before=len(links)
        for url,title in rows: links.setdefault(url,title)
        if len(links)>=expected: break
        if not rows or len(links)==before: raise ValueError("pagination exhausted before authoritative total")
        page+=1
    if expected is None or len(links)!=expected: raise ValueError(f"authoritative total mismatch: {len(links)} != {expected}")
    jobs=[parse_detail(url,fetcher(url),title) for url,title in sorted(links.items())]
    if len({j["job_id"] for j in jobs})!=len(jobs): raise ValueError("duplicate job ids")
    return Inventory(tuple(jobs),expected)
