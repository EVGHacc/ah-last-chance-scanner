#!/usr/bin/env python3
"""Bounded read-only diagnostics for N26 and Revolut official vacancy coverage."""
import json,re,requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128 Safari/537.36","Accept-Language":"en-GB,en;q=0.9"}
U={
"N26_LIST":"https://n26.com/en-eu/careers",
"N26_TARGET":"https://n26.com/en-eu/careers/positions/7845376",
"N26_APPLY":"https://n26.com/en-eu/careers/positions/7845376/apply",
"REV_LIST":"https://www.revolut.com/careers/",
"REV_RISK_TEAM":"https://www.revolut.com/careers/team/risk-compliance-audit/",
"REV_CRIME_TEAM":"https://www.revolut.com/careers/team/support-fincrime/",
"REV_LEAD":"https://www.revolut.com/careers/position/financial-crime-compliance-lead-42af5ac2-1c89-44ee-b0eb-bad4124ec2ab/",
"REV_HEAD_UK":"https://www.revolut.com/careers/position/head-of-financial-crime-fraud-risk-6777d9e3-caf3-48e0-93ef-80e39230b1c7/",
"REV_HEAD_EU":"https://www.revolut.com/careers/position/head-of-financial-crime-fraud-risk-34647acd-dc06-4897-a30a-f1cca93abc87/",
"REV_CCO":"https://www.revolut.com/careers/position/chief-compliance-officer-wealth-trading-ffdf2318-a97f-4a71-93ed-bc3e00ea2f12/",
"REV_GOV":"https://www.revolut.com/careers/position/financial-crime-compliance-governance-manager-158b9187-b51d-4674-9409-510565ca8a3b/",
}
for label,u in U.items():
 try:
  r=requests.get(u,headers=H,timeout=13)
  s=BeautifulSoup(r.text,"html.parser")
  positions=[(a.get_text(" ",strip=True)[:95],urljoin(r.url,a.get("href"))) for a in s.select("a[href]")
             if re.search(r"/(?:position|positions|apply)/",a.get("href",""),re.I)]
  scripts=s.find_all("script")
  idhits={x:bool(x in r.text) for x in ("7845376","42af5ac2","6777d9e3","34647acd","ffdf2318","158b9187")}
  forms=[(f.get("action"),f.get("method"),len(f.find_all(["input","button","select","textarea"]))) for f in s.select("form")][:4]
  buttons=[(x.name,x.get_text(" ",strip=True)[:60],x.get("href"),x.get("type")) for x in s.find_all(["a","button","input"])
          if re.search(r"\bapply\b|solliciteer|submit",x.get_text(" ",strip=True)+" "+str(x.get("value","")),re.I)][:7]
  chunks=[(len(t.get_text() or ""), (t.get("id") or t.get("type") or "")[:90], (t.get_text() or "")[:80]) for t in scripts if len(t.get_text() or "")>30000][:6]
  meta=[(x.get("name") or x.get("property"),x.get("content","")[:85]) for x in s.find_all("meta") if re.search("description|og:title",str(x),re.I)][:3]
  print("ORG_PROBE",label,r.status_code,r.url,"bytes",len(r.content),
       "title",s.title.get_text(" ",strip=True)[:100] if s.title else None,
       "jobLinks",len(positions),"unique",len(set(u for _,u in positions)),
       "first",positions[:3],"last",positions[-3:],"idHits",idhits,
       "forms",forms,"apply",buttons,"scriptCount",len(scripts),"largeScripts",chunks,"meta",meta,flush=True)
 except Exception as e:print("ORG_ERROR",label,type(e).__name__,str(e)[:200],flush=True)
