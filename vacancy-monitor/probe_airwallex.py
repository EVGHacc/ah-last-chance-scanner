#!/usr/bin/env python3
"""Short non-mutating probe of Airwallex's public first-party career inventory."""
import json, re, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs

H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
urls=[
 "https://careers.airwallex.com/jobs/",
 "https://careers.airwallex.com/jobs/?e-page-9075d2b=2",
 "https://careers.airwallex.com/jobs/?order=newest&page=2",
 "https://careers.airwallex.com/jobs/?order=newest&paged=2",
 "https://careers.airwallex.com/robots.txt",
 "https://careers.airwallex.com/wp-sitemap.xml",
 "https://careers.airwallex.com/sitemap_index.xml",
 "https://api.ashbyhq.com/posting-api/job-board/airwallex",
]
targets={"ad877e85-6c71-4e6b-afc7-3d87b9488adb",
         "004af48d-83e6-44c0-9ed0-493142195481",
         "15a5d8b4-a5fd-4b4d-a933-387702221b75"}
for u in urls:
 try:
  r=requests.get(u,headers=H,timeout=10)
  print("PROBE",r.status_code,r.url,"bytes",len(r.content),"type",r.headers.get("content-type"),flush=True)
  body=r.text
  if "json" in r.headers.get("content-type","").lower() and r.status_code==200:
   j=r.json()
   arr=j.get("jobs",[]) if isinstance(j,dict) else []
   print("JSON", "keys",list(j)[:10] if isinstance(j,dict) else type(j).__name__,
         "jobs",len(arr),"titles",[(x.get("title"),x.get("jobUrl"),x.get("applyUrl")) for x in arr[:4]],
         "targetHits",[(x.get("title"),x.get("jobUrl")) for x in arr if any(t in json.dumps(x) for t in targets)],flush=True)
  else:
   soup=BeautifulSoup(body,"html.parser")
   entries=[(a.get_text(" ",strip=True)[:90],urljoin(r.url,a["href"]))
            for a in soup.find_all("a",href=True) if "/job/" in a["href"]]
   pages=[(a.get_text(" ",strip=True)[:40],a["href"]) for a in soup.find_all("a",href=True)
          if re.search(r"(page|pag|order|next|e-page)",a["href"],re.I)]
   print("HTML","title",soup.title.get_text(" ",strip=True) if soup.title else None,
         "jobLinks",len(entries),"samples",entries[:3],"pagination",pages[:20],
         "targetIdsInHtml",[t for t in targets if t in body],
         "scriptSrc",[x.get("src","") for x in soup.find_all("script",src=True) if re.search(r"(job|career|app)",x.get("src",""),re.I)][:8],flush=True)
 except Exception as e:
  print("PROBE ERROR",u,type(e).__name__,str(e)[:170],flush=True)
