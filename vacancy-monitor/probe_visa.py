#!/usr/bin/env python3
"""Read-only probe of Visa's official Workday inventory and one exact vacancy."""
import re, requests
from bs4 import BeautifulSoup
base="https://visa.wd5.myworkdayjobs.com"
feed=base+"/wday/cxs/visa/Visa/jobs"
path="/GB---London-United-Kingdom/Director--Rules-Governance-and-Transformation_REF088281W"
target="REF088281W"
headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36",
         "Accept-Language":"en-US,en;q=0.9","Accept":"application/json, text/plain, */*"}
s=requests.Session()
def post(query, offset=0, limit=20):
    try:
        r=s.post(feed,headers=headers,json={"limit":limit,"offset":offset,"searchText":query,"appliedFacets":{}},timeout=12)
        print("VISA_PAGE",repr(query),offset,"status",r.status_code,"final",r.url,"bytes",len(r.content),flush=True)
        if r.status_code!=200:return
        j=r.json();jobs=j.get("jobPostings",[])
        print("VISA_TOTAL",repr(query),offset,"total",j.get("total"),"count",len(jobs),"first",
              [(x.get("title"),x.get("externalPath")) for x in jobs[:2]],
              "matches",[(x.get("title"),x.get("externalPath")) for x in jobs if target in str(x)],flush=True)
    except Exception as e: print("VISA_PAGE_ERROR",repr(query),offset,type(e).__name__,str(e)[:160],flush=True)
for q,offset in (("",0),("",20),("",40),("REF088281W",0),("Rules Governance",0)):
    post(q,offset)
urls=[base+"/en-US/Visa/job"+path,base+"/wday/cxs/visa/Visa/job"+path,
      base+"/en-US/Visa/job"+path+"/apply",base+"/Visa/job"+path]
for u in urls:
 try:
    r=s.get(u,headers=headers,timeout=12)
    c=r.headers.get("content-type","")
    print("VISA_DETAIL",r.status_code,r.url,"bytes",len(r.content),"type",c,flush=True)
    if "json" in c and r.status_code==200:
       j=r.json();p=j.get("jobPostingInfo",{})
       print("VISA_DETAIL_JSON","title",p.get("title"),"id",p.get("jobReqId"),
             "posted",p.get("postedOn"),"jobId",p.get("jobId"),"externalUrl",p.get("externalUrl"),
             "keys",list(p)[:25],"hasDescription",bool(p.get("jobDescription")),flush=True)
    else:
       soup=BeautifulSoup(r.text,"html.parser")
       print("VISA_DETAIL_HTML","title",soup.title.get_text(" ",strip=True) if soup.title else None,
             "idInBody",target in r.text,"applyControl",bool(re.search(r'apply now|submit application',r.text,re.I)),flush=True)
 except Exception as e:print("VISA_DETAIL_ERROR",u,type(e).__name__,str(e)[:160],flush=True)
