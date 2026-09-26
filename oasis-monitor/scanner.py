#!/usr/bin/env python3
"""Public-page Oasis resale monitor. Explicit uncertainty; never treats an index quote as a sold ticket.

Only ordinary public browsing. No login, bypass, buying, private endpoints or payments.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
AMSTERDAM = ZoneInfo('Europe/Amsterdam')
DATES = ('2027-07-16', '2027-07-17')
BLOCKED = re.compile(r'captcha|are you a robot|verify you are human|access denied|unusual traffic|toegang geweigerd|enable cookies to continue|security challenge|automated requests', re.I)
PRICE = re.compile(r'(?:(?:€|EUR)\s*([\d.,]+)|([\d.,]+)\s*(?:€|EUR))', re.I)
CATEGORIES = [
    ('front_standing', re.compile(r'front\s*(?:standing|pitch)|front\s*(?:staan|general admission)|golden circle', re.I)),
    ('rear_standing', re.compile(r'rear\s*(?:standing|pitch)|rear\s*(?:staan|general admission)|general admission|staanplaatsen|standing', re.I)),
    ('vip', re.compile(r'\bVIP\b|hospitality|package|pakket', re.I)),
    ('seated', re.compile(r'\b(?:section|block|vak|row|rij|seat|zitplaatsen|seated)\b', re.I)),
]
MONTHS = {'07': ('jul', 'juli', 'july')}
TARGETS = {
    'ticketmaster': ['https://www.ticketmaster.nl/artist/oasis-tickets/3668'] * 2,
    'stubhub-nl': ['https://www.stubhub.nl/', 'https://www.stubhub.nl/oasis-tickets-amsterdam-johan-cruijff-arena-17-7-2027/event/107667902/'],
    'stubhub-international': ['https://www.stubhub.com/oasis-amsterdam-tickets-7-16-2027/event/162088409/', 'https://www.stubhub.com/oasis-amsterdam-tickets-7-17-2027/event/162088410/'],
    'viagogo': ['https://www.viagogo.com/au/Concert-Tickets/E-162088409', 'https://www.viagogo.com/au/Concert-Tickets/E-162088410'],
    'ticketswap': ['https://www.ticketswap.nl/concert-tickets/oasis-amsterdam-johan-cruijff-arena-2027-07-16-CfBM59Cy8Y6WBxcy8fet1', 'https://www.ticketswap.nl/search?query=Oasis'],
    'ticombo': ['https://www.ticombo.com/en/discover/event/oasis-2707162359', 'https://www.ticombo.com/en/discover/event/oasis-2707172359'],
    'gigsberg': ['https://www.gigsberg.com/concert-tickets/rock/oasis-tickets'] * 2,
    'tixel': ['https://tixel.com/'] * 2,
    'seatpick': ['https://seatpick.com/oasis-tickets'] * 2,
    'eventworld': ['https://www.eventworld.com/oasis-amsterdam-tickets-16-07-2027/event/562155', 'https://www.eventworld.com/oasis-amsterdam-tickets-17-07-2027/event/562153'],
}
FORUMS = {
    'reddit-oasis': 'https://www.reddit.com/r/oasis/new/.rss',
    'reddit-tickets': 'https://www.reddit.com/r/Tickets/new/.rss',
    'reddit-concerts': 'https://www.reddit.com/r/concerts/new/.rss',
    'festivalsunited': 'https://www.festivalsunited.com/forum/topic/35767',
    'viva': 'https://forum.viva.nl/entertainment/oasis-tour-2027/list_messages/516143',
    'live4ever': 'https://live4ever.proboards.com/',
}


def now() -> str:
    return datetime.now(AMSTERDAM).isoformat(timespec='seconds')


def contains_date(text: str, date: str) -> bool:
    day = int(date[-2:]); dd = f'{day:02d}'
    s = re.sub(r'\s+', ' ', text.lower())
    patterns = [rf'\b{dd}[-/.]07[-/.]2027\b', rf'\b2027[-/.]07[-/.]{dd}\b', rf'\b{day}\s*(?:jul|juli|july)[a-z]*\s*,?\s*2027\b', rf'\b(?:jul|juli|july)[a-z]*\s*{day}\s*,?\s*2027\b', rf'\b7[-/.]{dd}[-/.]2027\b', rf'\b{day}[-/.]7[-/.]2027\b']
    return any(re.search(p, s, re.I) for p in patterns)


def is_event(text: str, url: str, date: str) -> bool:
    s = text.lower()
    path = urllib.parse.urlparse(url).path.lower()
    if not ('oasis' in s and ('amsterdam' in s or 'cruijff' in s or 'cruyff' in s)):
        return False
    if ('hotel package' in s or 'hotel pakketten' in s) and len(s) < 350:
        return False
    # A singer index containing BOTH Amsterdam dates is not a dated event page.
    if re.search(r'(performer|artist|music-tickets|/search|/venue/|oasis-tickets/?$)', path):
        return False
    if re.search(r'(?:2027[-/.]07[-/.](?:16|17)|(?:16|17)[-/.]0?7[-/.]2027|0?7[-/.](?:16|17)[-/.]2027)', path):
        return contains_date(path,date)
    return contains_date(s, date)


def money(raw: str) -> float | None:
    s = raw.strip().replace(' ', '').replace('\u00a0','')
    if not re.fullmatch(r'[0-9][0-9,.]*', s):
        return None
    if ',' in s and '.' in s:
        s = s.replace(',', '') if s.rfind('.') > s.rfind(',') else s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.') if len(s.split(',')[-1]) <= 2 else s.replace(',', '')
    elif '.' in s and len(s.split('.')[-1]) == 3:
        s = s.replace('.', '')
    value = float(s)
    return round(value,2) if 10 <= value <= 10000 else None


def prices(text: str) -> list[float]:
    return [v for m in PRICE.finditer(text) if (v := money(m.group(1) or m.group(2))) is not None]


def classify(text: str) -> tuple[str | None, str | None]:
    for name, rx in CATEGORIES:
        if rx.search(text):
            m = re.search(r'\b(?:section|block|vak|row|rij)\s*[A-Za-z0-9-]{1,8}', text, re.I)
            return name, m.group(0) if m else None
    return None, None


def extract_cards(cards: list[dict], date: str, source: str, url: str, checked_at: str) -> list[dict]:
    out = []
    seen = set()
    for card in cards[:300]:
        text = re.sub(r'\s+', ' ', card.get('text','')).strip()
        if len(text) < 8 or len(text) > 1300:
            continue
        amounts = prices(text)
        cat, section = classify(text)
        if not amounts or not cat:
            continue
        # Never mix a package/parking price with ordinary standing.
        if re.search(r'parking|parkeren|hotel', text, re.I) and cat != 'vip':
            continue
        href = card.get('href') or url
        key = hashlib.sha256(f'{source}|{date}|{href}|{text[:150]}'.encode()).hexdigest()[:20]
        if key in seen:
            continue
        seen.add(key)
        fees = bool(re.search(r'fees included|incl(?:usive|usief)?\.?\s*(?:fees|kosten)|all[- ]in|including fees', text, re.I))
        count_match = re.search(r'\b(\d{1,2})\s*(?:tickets|kaartjes|places)\b', text, re.I)
        count = int(count_match.group(1)) if count_match else None
        out.append(dict(date=date,source=source,listingId=key,category=cat,section=section,
                        askingPriceEur=min(amounts),allIn=True if fees else None,feeKnown=fees,
                        listingCount=1,ticketCount=count,evidenceUrl=href,checkedAt=checked_at,
                        evidenceType='visible_listing_card',sample=text[:300]))
    return out


def extract_eventworld(text: str, date: str, url: str, checked_at: str) -> list[dict]:
    # Aggregator quotes are not underling seller tickets and never count as verified listings.
    rows = []
    for name in ('viagogo','StubHub International','StubHub','Ticombo'):
        matches = re.findall(rf'\b{re.escape(name)}\b(?:\s+\d[\d,]*\s+available)?(?:\s+Best\s+price)?\s+from\s+([\d.,]+)\s*€', text, re.I)
        if matches:
            val = money(matches[0]);
            if val is not None:
                rows.append(dict(date=date,source='eventworld',partner=name,category=None,askingPriceEur=val,
                                 listingCount=None,ticketCount=None,allIn=None,feeKnown=False,
                                 evidenceType='aggregator_quote',evidenceUrl=url,checkedAt=checked_at))
    return rows


def ticketswap_counts(text: str) -> dict | None:
    match = re.search(r'\b([\d.,]+)\s*(?:Beschikbaar|Available)\s*[•|·]\s*([\d.,]+)\s*(?:Verkocht|Sold)\s*[•|·]\s*([\d.,]+)\s*(?:Gezocht|Wanted|Searching)',text,re.I)
    if match:
        return {'available':int(match.group(1).replace('.','').replace(',','')),'soldPlatformCounter':int(match.group(2).replace('.','').replace(',','')),'wanted':int(match.group(3).replace('.','').replace(',',''))}
    return None


def discover(links: list[dict], date: str, domain: str) -> str | None:
    # Must be a coherent single event card: do not use the full artist page's dates.
    candidates=[]
    for a in links:
        text=re.sub(r'\s+',' ',a.get('context') or a.get('text') or '')[:500]
        href=a.get('href') or ''
        if not href.startswith('http') or urllib.parse.urlparse(href).netloc.lower().removeprefix('www.') != domain.removeprefix('www.'):
            continue
        if not contains_date(text,date) or not re.search(r'oasis',text,re.I):
            continue
        if re.search(r'hotel\s*package|ticket\s*\+\s*hotel|parking|parkeren',text,re.I):
            continue
        if 'amsterdam' not in text.lower() and 'arena' not in text.lower():
            continue
        candidates.append((len(href),href))
    return sorted(candidates)[0][1] if candidates else None


def validate_snapshot(snapshot: dict, registry: dict) -> None:
    expected={(date,s['id']) for date in DATES for s in registry['sources']}
    got=[(c['date'],c['source']) for c in snapshot['checks']]
    assert len(expected)==20 and len(got)==20 and set(got)==expected,'20 distinct source/date records required'
    valid={'verified_prices','verified_no_listings','blocked_or_login','technical_failure','not_listed','unverified'}
    for c in snapshot['checks']:
        assert c['checkStatus'] in valid and c.get('checkedAt') and c.get('evidenceUrl')
        if c['checkStatus'].startswith('verified'):
            assert c.get('eventValidated') and c.get('evidenceUrl').startswith('https://')
    for d in DATES:
        rows=[c for c in snapshot['checks'] if c['date']==d]
        c=snapshot['sourceCoverage'][d]
        assert c['total']==10
        assert c['pageVerified']==sum(x['eventValidated'] for x in rows)
        assert c['listingVerified']==sum(x['listingVerified'] for x in rows)
        assert c['allInVerified']==sum(x['allInVerified'] for x in rows)
        assert c['pageVerified']>=c['listingVerified']>=c['allInVerified']
    for item in snapshot['listings']:
        assert item['date'] in DATES and item['source'] in {s['id'] for s in registry['sources']}
        assert item.get('evidenceUrl') and item.get('askingPriceEur') is not None
        assert item['evidenceType'] in ('aggregator_quote','visible_listing_card','event_from_price')


def summary(snapshot: dict) -> str:
    lines=[f"Oasis {snapshot['date']} {snapshot['checkedAt']} — {snapshot['status']}"]
    for d in DATES:
        c=snapshot['sourceCoverage'][d]
        lines.append(f"{d}: page {c['pageVerified']}/10, listing {c['listingVerified']}/10, all-in {c['allInVerified']}/10")
        quotes=sorted([o for o in snapshot['listings'] if o['date']==d],key=lambda x:x['askingPriceEur'])
        for o in quotes[:8]:
            lines.append(f"  {o['source']} {o.get('partner') or o.get('category') or '?'} €{o['askingPriceEur']:.2f} {o['evidenceType']} fees:{o['allIn']} {o['evidenceUrl']}")
    for c in snapshot['checks']:
        if c['checkStatus'] not in ('verified_prices','verified_no_listings'):
            lines.append(f"{c['date']} {c['source']}: {c['checkStatus']} {c['note'][:110]}")
    lines.append(f"Forum signals {len(snapshot['forumSignals'])}; forum failures {sum(x['status']!='ok' for x in snapshot['forumChecks'])}; snapshot qa PASS")
    return '\n'.join(lines)


async def fetch_page(context, url: str, timeout: int) -> dict:
    page=await asyncio.wait_for(context.new_page(),timeout=12)
    result={'url':url,'status':None,'text':'','html':'','links':[],'cards':[],'error':None,'checkedAt':now()}
    try:
        response=await page.goto(url, wait_until='domcontentloaded', timeout=timeout*1000)
        result['status']=response.status if response else None
        if result['status'] in (401,403,429):
            result['error']=f'HTTP {result["status"]}';return result
        await page.wait_for_timeout(1000)
        # One gentle scroll for lazy-loaded public listings; no interactions with login or checkout.
        if not BLOCKED.search((await asyncio.wait_for(page.title(),timeout=6))[:200]):
            await page.mouse.wheel(0,700);await page.wait_for_timeout(500)
        result['url']=page.url
        result['text']=(await page.locator('body').inner_text(timeout=4000))[:120000]
        result['html']=(await asyncio.wait_for(page.content(),timeout=8))[:300000]
        result['links']=await asyncio.wait_for(page.locator('a[href]').evaluate_all("""els=>els.slice(0,700).map(a=>({href:a.href,text:(a.innerText||'').trim(),context:(a.closest('article,li,[data-testid*=event],[class*=event],[class*=Event]')?.innerText||a.parentElement?.innerText||'').slice(0,500)}))"""),timeout=8)
        result['cards']=await asyncio.wait_for(page.locator('article,[data-testid*=listing],[data-test*=listing],[class*=ListingCard],[class*=TicketCard]').evaluate_all("""els=>els.slice(0,300).map(e=>({text:(e.innerText||'').slice(0,1300),href:e.querySelector('a[href]')?.href||''}))"""),timeout=8)
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {str(exc)[:180]}'
    finally:
        result['checkedAt']=now()
        try:
            await asyncio.wait_for(page.close(),timeout=8)
        except Exception:
            pass
    return result


async def scan_one(context, sem, source: dict, date: str, timeout: int) -> tuple[dict,list[dict]]:
    sid=source['id'];index=DATES.index(date);url=TARGETS[sid][index]
    async with sem:
        first=await fetch_page(context,url,timeout)
        current=first
        # Only try to discover an event from a reachable public artist/search index.
        if not first['error'] and not BLOCKED.search(first['text'][:1500]):
            if not is_event(first['text'],first['url'],date):
                found=discover(first['links'],date,urllib.parse.urlparse(first['url']).netloc.lower())
                if found and found!=first['url']:
                    current=await fetch_page(context,found,timeout)
    checked=current['checkedAt'];base=dict(date=date,source=sid,sourceType=source['type'],checkedAt=checked,evidenceUrl=current['url'],
        checkStatus='unverified',eventValidated=False,listingVerified=False,allInVerified=False,
        listingCount=None,ticketCount=None,route='browser',note='',httpStatus=current['status'])
    items=[]
    text=current['text'];url=current['url']
    if current['error']:
        base.update(checkStatus='blocked_or_login' if current['status'] in (401,403,429) else 'technical_failure',note=current['error']);return base,items
    if BLOCKED.search(text[:1800]):
        base.update(checkStatus='blocked_or_login',note='Public page requests human verification/access restriction');return base,items
    if not text or len(text)<100:
        base.update(checkStatus='unverified',note='Page rendered without sufficient readable event content');return base,items
    if not is_event(text,url,date):
        base.update(checkStatus='not_listed' if current is first else 'unverified',note='No exact dated Amsterdam event proven; index cannot be used as quote');return base,items
    base['eventValidated']=True
    if sid=='ticketswap':
        c=ticketswap_counts(text)
        if c is not None:
            base.update(listingCount=c['available'],ticketCount=None,marketCounters=c)
            if c['available']==0:
                base.update(checkStatus='verified_no_listings',listingVerified=True,note='Explicit zero available on dated event page');return base,items
    if sid=='eventworld':
        items=extract_eventworld(text,date,url,checked)
        if items:
            base.update(checkStatus='verified_prices',note='Aggregator quotes only: partner links not seller-verified; category and fees unknown');return base,items
    items=extract_cards(current['cards'],date,sid,url,checked)
    if items:
        base.update(checkStatus='verified_prices',listingVerified=True,allInVerified=any(x['allIn'] is True for x in items),
                    listingCount=len(items),ticketCount=sum(x['ticketCount'] or 0 for x in items) if all(x['ticketCount'] is not None for x in items) else None,
                    note='DOM-visible categorized listing cards; totals may be partial due to pagination')
    else:
        base.update(checkStatus='unverified',note='Dated event opened, but no category-level live listing prices verified')
    return base,items


async def scan_forums(context, sem, timeout: int) -> tuple[list[dict],list[dict]]:
    async def one(source,url):
        async with sem:
            p=await fetch_page(context,url,timeout)
        status='failed' if p['error'] else 'ok'
        result=dict(source=source,url=url,checkedAt=p['checkedAt'],status=status,note=p['error'] or '')
        signals=[]
        if not p['error'] and source.startswith('reddit'):
            # Reddit RSS is public; only timestamped, individual relevant posts qualify.
            soup=BeautifulSoup(p['html'],'html.parser')
            for entry in soup.find_all('entry')[:30]:
                title=entry.find('title').get_text(' ',strip=True) if entry.find('title') else ''
                link=entry.find('link');href=link.get('href') if link else ''
                published=entry.find('published')
                dt=published.get_text(strip=True) if published else None
                if not (re.search(r'oasis|amsterdam',title,re.I) and re.search(r'ticket|resale|amsterdam|transfer|face.value|2027|sale',title,re.I) and href and dt):
                    continue
                try: recent=datetime.now(timezone.utc)-datetime.fromisoformat(dt.replace('Z','+00:00')) < timedelta(days=7)
                except ValueError: recent=False
                if recent: signals.append(dict(source=source,date=dt,url=href,type='fan_post_unverified',summary=title[:180]))
        return result,signals
    rows=await asyncio.gather(*(one(k,v) for k,v in FORUMS.items()))
    return [r for r,_ in rows],[s for _,signals in rows for s in signals][:15]


def compare(previous: dict, current: dict) -> list[dict]:
    if previous.get('status') in ('awaiting_first_scan',None):return []
    before={(x['date'],x['source'],x.get('partner'),x.get('category'),x.get('evidenceType'),x.get('allIn')):x for x in previous.get('listings',[])}
    changes=[]
    for x in current['listings']:
        k=(x['date'],x['source'],x.get('partner'),x.get('category'),x.get('evidenceType'),x.get('allIn'))
        old=before.get(k)
        if old and old['askingPriceEur']>0:
            changes.append(dict(date=x['date'],source=x['source'],category=x.get('category'),partner=x.get('partner'),before=old['askingPriceEur'],after=x['askingPriceEur'],percent=round(100*(x['askingPriceEur']/old['askingPriceEur']-1),1),basis=x['evidenceType']))
    return changes


async def main(args):
    registry=json.loads((ROOT/'sources.json').read_text())
    assert [s['id'] for s in registry['sources']]==list(TARGETS),'Registry does not match fixed ten-source target mapping'
    previous_path=ROOT/'data/latest.json'
    previous=json.loads(previous_path.read_text()) if previous_path.exists() else {}
    async with async_playwright() as pw:
        browser=await asyncio.wait_for(pw.chromium.launch(headless=True, **({'executable_path':shutil.which('chromium')} if shutil.which('chromium') else {})),timeout=40)
        context=await asyncio.wait_for(browser.new_context(locale='nl-NL',timezone_id='Europe/Amsterdam',viewport={'width':1365,'height':920},user_agent=None),timeout=15)
        sem=asyncio.Semaphore(args.workers)
        jobs=[scan_one(context,sem,s,date,args.timeout) for date in DATES for s in registry['sources']]
        rows=await asyncio.gather(*(asyncio.wait_for(job,timeout=200) for job in jobs),return_exceptions=True)
        checks=[];listings=[]
        for idx,row in enumerate(rows):
            if isinstance(row,BaseException):
                date=DATES[idx//10];s=registry['sources'][idx%10];checks.append(dict(date=date,source=s['id'],sourceType=s['type'],checkedAt=now(),evidenceUrl=TARGETS[s['id']][DATES.index(date)],checkStatus='technical_failure',eventValidated=False,listingVerified=False,allInVerified=False,listingCount=None,ticketCount=None,route='browser',note=f'{type(row).__name__}: {str(row)[:150]}',httpStatus=None))
            else:
                c,ls=row;checks.append(c);listings.extend(ls)
        try:
            forumChecks,forumSignals=await asyncio.wait_for(scan_forums(context,sem,args.timeout),timeout=110)
        except Exception as exc:
            forumChecks=[dict(source=k,url=u,checkedAt=now(),status='failed',note=f'Forum timeout/failure: {type(exc).__name__}') for k,u in FORUMS.items()]
            forumSignals=[]
        async with sem:
            try:
                official=await asyncio.wait_for(fetch_page(context,'https://help.ticketmaster.nl/hc/nl/articles/50379069472529-Oasis-Live-27',args.timeout),timeout=45)
            except Exception as exc:
                official=dict(url='https://help.ticketmaster.nl/hc/nl/articles/50379069472529-Oasis-Live-27',checkedAt=now(),error=f'{type(exc).__name__}',status=None,text='')
        try:
            await asyncio.wait_for(browser.close(),timeout=10)
        except Exception:
            pass
    coverage={d:{'pageVerified':sum(c['eventValidated'] for c in checks if c['date']==d),'listingVerified':sum(c['listingVerified'] for c in checks if c['date']==d),'allInVerified':sum(c['allInVerified'] for c in checks if c['date']==d),'total':10} for d in DATES}
    snap=dict(schemaVersion=2,date=datetime.now(AMSTERDAM).date().isoformat(),checkedAt=now(),complete=True,status='classified_with_gaps',sourceCoverage=coverage,
              checks=checks,listings=listings,forumChecks=forumChecks,forumSignals=forumSignals,changes=compare(previous,dict(listings=listings)),
              policy=dict(source=official['url'],checkedAt=official['checkedAt'],status='verified_page' if not official['error'] and 'oasis' in official['text'].lower() else 'unverified',httpStatus=official['status'],textHash=hashlib.sha256(official['text'].encode()).hexdigest() if official['text'] else None,summary='Official ticket conditions must be read in full before interpreting external resale or transfer.'),
              notes=['Aggregator quotes are kept separate from platform-confirmed listing-level evidence. Missing/blocked sources are not zero.', 'Category-specific all-in comparison requires visible evidence; no inferred fee or completed sale.'])
    if all(x['pageVerified']==10 and x['listingVerified']==10 and x['allInVerified']==10 for x in coverage.values()):snap['status']='fully_verified'
    validate_snapshot(snap,registry)
    print(summary(snap),flush=True)
    if not args.dry_run:
        out=ROOT/'data'/f"{snap['date']}.json"
        out.parent.mkdir(parents=True,exist_ok=True)
        # Never silently overwrite immutable history from another run of this date.
        if out.exists():
            existing=json.loads(out.read_text())
            if existing.get('checkedAt')==snap['checkedAt']:
                raise RuntimeError('Refusing to overwrite existing exact-timestamp snapshot')
        for dest in (out,ROOT/'data/latest.json'):
            temp=dest.with_suffix('.json.tmp')
            temp.write_text(json.dumps(snap,indent=2,ensure_ascii=False)+'\n')
            os.replace(temp,dest)
        validate_snapshot(json.loads(out.read_text()),registry)
        validate_snapshot(json.loads((ROOT/'data/latest.json').read_text()),registry)
        assert out.read_bytes()==(ROOT/'data/latest.json').read_bytes()
        print(f'SNAPSHOT_READBACK_PASS path={out} checks=20',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--timeout',type=int,default=18);p.add_argument('--workers',type=int,default=3);p.add_argument('--dry-run',action='store_true')
    asyncio.run(main(p.parse_args()))
