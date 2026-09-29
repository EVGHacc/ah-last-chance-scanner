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

# Inspect first-party paging controls and the exact same-vacancy apply workflow,
# without POSTing data or submitting an application.
page=requests.get(URLS["BOARD"],headers=H,timeout=13)
sp=BeautifulSoup(page.text,"html.parser")
for a in sp.find_all(["a","button","input","select","form"]):
 attrs={k:v for k,v in a.attrs.items() if k in ("href","action","name","value","data-page","data-url","data-page-number","id","class","type","onclick")}
 label=a.get_text(" ",strip=True)[:80]
 if re.search(r"next|page|pagination|results per|view more|show more|load more|search",label+" "+str(attrs),re.I):
  print("WISE_PAGING",a.name,label,attrs,flush=True)
for term in ("window.siteId","attrax-vacancy", "pagination", "nextPage", "pageNo", "pageSize", "searchResults", "/Vacancies/", "loadMore", "Take"):
 matches=list(re.finditer(re.escape(term),page.text,re.I))
 print("WISE_TERM",term,"count",len(matches),"sample",
       [page.text[max(0,m.start()-160):m.start()+300].replace("\n"," ")[:460] for m in matches[-3:]],flush=True)
for label,ident in (("LEAD","3054"),("MANAGER","3928"),("SENIOR_RISK","3822"),("ASSETS","3861")):
 u="https://wise.jobs/Workflow?workflowId=e845dd41-c192-48c4-80f2-85eafdf6039b&vacancyId="+ident
 try:
  r=requests.get(u,headers=H,timeout=13)
  soup=BeautifulSoup(r.text,"html.parser")
  print("WISE_APPLY",label,r.status_code,r.url,"bytes",len(r.content),
        "title",soup.title.get_text(" ",strip=True)[:90] if soup.title else "",
        "identity",ident in r.text,"forms",len(soup.select("form")),"fields",len(soup.select("input")),
        "closed",bool(re.search(r"job closed|vacancy closed|no longer available|applications closed|expired|not found",soup.get_text(" ",strip=True),re.I)),
        "submit_labels",[x.get_text(" ",strip=True)[:40] for x in soup.select("button,input[type=submit]")][-6:],
        flush=True)
 except Exception as e:print("WISE_APPLY_ERROR",label,type(e).__name__,str(e)[:180],flush=True)

# The first-party Wise application endpoint redirects to SmartRecruiters/Wise.
# Check that publisher's public ATS listing with official totals and query.
for company in ("Wise","wise"):
 for q in ("","Compliance Lead (Wise Platform)","Compliance Manager: Group Regulatory Compliance","Senior Risk Manager","Group Lead - Assets Risk"):
  try:
   resp=requests.get(f"https://api.smartrecruiters.com/v1/companies/{company}/postings",headers=H,
                     params={"limit":100,"offset":0,"destination":"PUBLIC","q":q},timeout=13)
   data=resp.json() if resp.status_code==200 else {}
   items=data.get("content",[]) if isinstance(data,dict) else []
   print("WISE_ATS",company,repr(q),resp.status_code,"total",data.get("totalFound") if isinstance(data,dict) else None,
         "returned",len(items),"first",[(x.get("id"),x.get("name"),x.get("jobAdUrl"),x.get("postingUrl")) for x in items[:2]],
         "matches",[(x.get("id"),x.get("name")) for x in items if q and q.lower() in str(x.get("name","")).lower()],
         flush=True)
  except Exception as e:print("WISE_ATS_ERROR",company,repr(q),type(e).__name__,str(e)[:140],flush=True)
