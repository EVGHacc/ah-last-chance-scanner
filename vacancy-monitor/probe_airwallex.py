#!/usr/bin/env python3
"""Short non-mutating probe of Airwallex's public first-party career inventory."""
import json, re, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

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
         "targetHits",[(x.get("title"),x.get("jobUrl"),x.get("location"),x.get("department"),x.get("team"),x.get("isListed"),list(x.keys())) for x in arr if any(t in json.dumps(x) for t in targets)],flush=True)
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


# Confirm the official site and the ATS still reference the same current posting.
for ident, slug in (
 ("ad877e85-6c71-4e6b-afc7-3d87b9488adb","senior-director-aml-sanctions-governance-policy"),
 ("004af48d-83e6-44c0-9ed0-493142195481","senior-director-of-risk-assurance-monitoring-framework-reporting"),
 ("15a5d8b4-a5fd-4b4d-a933-387702221b75","senior-director-eu-me-mlro"),
):
 for hosturl in (
  f"https://careers.airwallex.com/job/{ident}/{slug}/",
  f"https://jobs.ashbyhq.com/airwallex/{ident}",
  f"https://jobs.ashbyhq.com/airwallex/{ident}/application",
 ):
  try:
   r=requests.get(hosturl,headers=H,timeout=12)
   soup=BeautifulSoup(r.text,"html.parser")
   title=soup.title.get_text(" ",strip=True) if soup.title else None
   applies=[(x.get_text(" ",strip=True)[:55],x.get("href")) for x in soup.find_all("a",href=True)
            if re.search(r"apply|solliciteer",x.get_text(" ",strip=True),re.I)]
   print("DETAIL_PROBE",ident,r.status_code,r.url,"title",title,"bytes",len(r.content),
         "id_in_response",ident in r.text,
         "apply_links",applies[:5],flush=True)
  except Exception as e:print("DETAIL_PROBE_ERR",ident,hosturl,str(e)[:160],flush=True)


# Run the exact new adapter and direct-detail validator against current public data.
from scanner import load_registry, api_inventory, strategic_inventory_match, validate_jobs, job_key
org=next(x for x in load_registry() if x["name"]=="Airwallex")
feed=api_inventory(org)
by_id={j["source_job_id"]:j for j in feed["jobs"]} if feed else {}
sample=[by_id[t] for t in ("ad877e85-6c71-4e6b-afc7-3d87b9488adb",
                         "15a5d8b4-a5fd-4b4d-a933-387702221b75") if t in by_id]
checks=validate_jobs(sample,{job_key(j["url"]) for j in feed["jobs"]} if feed else set())
print("AIRWALLEX_ADAPTER_SMOKE",
      "api_complete",feed["complete"] if feed else None,
      "published_count",feed["official_total"] if feed else None,
      "relevant_count",sum(strategic_inventory_match(j) for j in feed["jobs"]) if feed else None,
      "error",feed["error"] if feed else "no result",
      "two_strong_ids_found",len(sample),
      "expired_id_published","004af48d-83e6-44c0-9ed0-493142195481" in by_id,
      "validation",[(j["title"],j["apply_live"],j["validation_reason"],j["url"],j["http_status"]) for j in checks],
      flush=True)
