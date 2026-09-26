"""Bound all browser operations and avoid a stuck page blocking the whole daily scan.

Idempotent on subsequent runs. Applied after the checksum-verified bootstrap.
"""
from pathlib import Path

path = Path(__file__).with_name("scanner.py")
src = path.read_text()
changes = [
("    page=await context.new_page()\n","    page=await asyncio.wait_for(context.new_page(),timeout=12)\n"),
("if not BLOCKED.search((await page.title())[:200]):","if not BLOCKED.search((await asyncio.wait_for(page.title(),timeout=6))[:200]):"),
("result['html']=(await page.content())[:300000]","result['html']=(await asyncio.wait_for(page.content(),timeout=8))[:300000]"),
("result['links']=await page.locator('a[href]').evaluate_all(","result['links']=await asyncio.wait_for(page.locator('a[href]').evaluate_all("),
(".slice(0,500)}))\"\"\")", ".slice(0,500)}))\"\"\"),timeout=8)"),
("result['cards']=await page.locator('article,[data-testid*=listing],[data-test*=listing],[class*=ListingCard],[class*=TicketCard]').evaluate_all(","result['cards']=await asyncio.wait_for(page.locator('article,[data-testid*=listing],[data-test*=listing],[class*=ListingCard],[class*=TicketCard]').evaluate_all("),
("href||''}))\"\"\")", "href||''}))\"\"\"),timeout=8)"),
("        result['checkedAt']=now();await page.close()","        result['checkedAt']=now()\n        try:\n            await asyncio.wait_for(page.close(),timeout=8)\n        except Exception:\n            pass"),
("browser=await pw.chromium.launch(headless=True,","browser=await asyncio.wait_for(pw.chromium.launch(headless=True,"),
(" if shutil.which('chromium') else {}))"," if shutil.which('chromium') else {})),timeout=40)"),
("context=await browser.new_context(locale='nl-NL',timezone_id='Europe/Amsterdam',viewport={'width':1365,'height':920},user_agent=None)","context=await asyncio.wait_for(browser.new_context(locale='nl-NL',timezone_id='Europe/Amsterdam',viewport={'width':1365,'height':920},user_agent=None),timeout=15)"),
("rows=await asyncio.gather(*jobs,return_exceptions=True)","rows=await asyncio.gather(*(asyncio.wait_for(job,timeout=200) for job in jobs),return_exceptions=True)"),
("        forumChecks,forumSignals=await scan_forums(context,sem,args.timeout)","        try:\n            forumChecks,forumSignals=await asyncio.wait_for(scan_forums(context,sem,args.timeout),timeout=110)\n        except Exception as exc:\n            forumChecks=[dict(source=k,url=u,checkedAt=now(),status='failed',note=f'Forum timeout/failure: {type(exc).__name__}') for k,u in FORUMS.items()]\n            forumSignals=[]"),
("            official=await fetch_page(context,'https://help.ticketmaster.nl/hc/nl/articles/50379069472529-Oasis-Live-27',args.timeout)\n        await browser.close()","            try:\n                official=await asyncio.wait_for(fetch_page(context,'https://help.ticketmaster.nl/hc/nl/articles/50379069472529-Oasis-Live-27',args.timeout),timeout=45)\n            except Exception as exc:\n                official=dict(url='https://help.ticketmaster.nl/hc/nl/articles/50379069472529-Oasis-Live-27',checkedAt=now(),error=f'{type(exc).__name__}',status=None,text='')\n        try:\n            await asyncio.wait_for(browser.close(),timeout=10)\n        except Exception:\n            pass")
]
updated=0
for old,new in changes:
    if old in src:
        src=src.replace(old,new,1)
        updated+=1
    elif new not in src:
        raise SystemExit(f"Unsupported scanner version / missing expected pattern: {old[:65]}")
path.write_text(src)
print(f"Browser hardening: {updated} changes; total={len(changes)}")
