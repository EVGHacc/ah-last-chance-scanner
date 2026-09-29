#!/usr/bin/env python3
"""Read-only Wise official board inventory and exact four-vacancy application probes."""
import json,re,requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin,urlparse
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36","Accept-Language":"en-GB,en;q=0.9"}
URLS={
"BOARD":"https://wise.jobs/jobs",
"LEAD":"https://wise.jobs/job/compliance-lead-wise-platform-in-london-jid-3054",
"MANAGER":"https://wise.jobs/job/compliance-manager-group-regulatory-compliance-in-london-jid-3928",
"SENIOR_RISK":"https://wise.jobs/job/senior-risk-manager-in-london-jid-3822",
"ASSETS":"https://wise.jobs/job/group-lead-assets-risk-in-london-jid-3861",
}
for label,url in URLS.items():
 try:
  r=requests.get(url,headers=H,timeout=13);s=BeautifulSoup(r.text,"html.parser")
  aa=[(x.get_text(" ",strip=True)[:95],urljoin(r.url,x.get("href",""))) for x in s.select("a[href]")
      if re.search(r"/job/.*-jid-\d+",x.get("href",""),re.I)]
  ids=sorted(set(re.findall(r"-jid-(\d+)",r.text,re.I)))
  ctl=[(x.name,x.get("href"),x.get("type"),x.get("action"),x.get_text(" ",strip=True)[:55],
        x.get("data-vacancyid"),x.get("data-job-id")) for x in s.find_all(["a","button","form","input"])
       if re.search("apply|submit|solliciteer",str(x.get("class",""))+" "+str(x.get("id",""))+" "+
       x.get_text(" ",strip=True)+" "+str(x.get("value","")),re.I)][:18]
  scripts=[x.get("src","") for x in s.find_all("script",src=True) if re.search("vacan|job|apply|api|career",x.get("src",""),re.I)][:15]
  snippets=[]
  for term in ("vacancyopjusttionswidget","3054","3928","3822","3861","Apply now","applybtn","jobdetails","api/"):
   i=r.text.lower().find(term.lower())
   if i>=0:snippets.append((term,r.text[max(0,i-140):i+280].replace("\n"," ")[:420]))
  print("WISE_PROBE",label,r.status_code,r.url,"size",len(r.content),
        "pageTitle",s.title.get_text(" ",strip=True)[:100] if s.title else None,
        "h1",s.h1.get_text(" ",strip=True)[:100] if s.h1 else None,
        "jobLinks",len(aa),"jobIds",len(ids),"sample",aa[:3],
        "targets",{v:v in ids for v in ("3054","3928","3822","3861")},
        "forms",len(s.select("form")),"applyControls",ctl,"scriptSources",scripts,
        "snippets",snippets[:7],flush=True)
 except Exception as e:print("WISE_PROBE_ERROR",label,type(e).__name__,str(e)[:170],flush=True)
