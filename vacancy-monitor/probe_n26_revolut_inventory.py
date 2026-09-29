#!/usr/bin/env python3
"""Non-mutating first-party source inventory and exact application-route checks."""
import json,re,requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
H={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36","Accept-Language":"en-GB,en;q=0.9"}
n26="https://n26.com/en-eu/careers"
rev="https://www.revolut.com/careers/"
for label,url in [("N26",n26),("REVOLUT",rev)]:
 r=requests.get(url,headers=H,timeout=15)
 html=r.text;soup=BeautifulSoup(html,"html.parser")
 ids=set(re.findall(r"/careers/positions/(\d{7,9})",html)) if label=="N26" else set(re.findall(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",html,re.I))
 print("INVENTORY",label,r.status_code,"bytes",len(html),"idcount",len(ids),"target",
       "7845376" in ids if label=="N26" else {t:t in html for t in ["42af5ac2","6777d9e3","34647acd","ffdf2318","158b9187"]},flush=True)
 if label=="N26":
  for target in ["7845376","8203585","Team Lead Non-Financial Risk and Internal Controls"]:
   i=html.find(target)
   print("N26_CONTEXT",target,"position",i,"snippet",html[max(0,i-380):i+470][:850],flush=True)
  scripts=[a.get_text() for a in soup.select("script") if "__reactRouterContext" in a.get_text()]
  print("N26_SERIALIZED",len(scripts),"script_chars",list(map(len,scripts)),"positions_unique",
        len(set(re.findall(r'positions/(\d{7,9})',"".join(scripts)))),flush=True)
 else:
  script=soup.find("script",id="__NEXT_DATA__")
  j=json.loads(script.get_text()) if script else {}
  print("REV_NEXT_ROOT",list(j),"pageprops",list(j.get("props",{}).get("pageProps",{})),flush=True)
  seen=[]
  def walk(v,path="",depth=0):
   if depth>16:return
   if isinstance(v,list):
    if len(v)>=15 and isinstance(v[0],dict):
     seen.append((path,len(v),list(v[0])[:15],str(v[0].get("title") or v[0].get("name") or "")[:90],
                  str(v[0].get("slug") or v[0].get("url") or "")[:110]))
    for ix,sub in enumerate(v):
     if isinstance(sub,(list,dict)):walk(sub,path+f"[{ix}]",depth+1)
   elif isinstance(v,dict):
    for k,sub in v.items():
     if isinstance(sub,(list,dict)):walk(sub,path+"."+k,depth+1)
  walk(j)
  print("REV_LARGE_LISTS",seen[:15],"total",len(seen),flush=True)
  for target in ["42af5ac2","6777d9e3","34647acd","ffdf2318","158b9187"]:
   raw=script.get_text();i=raw.find(target)
   print("REV_CONTEXT",target,"position",i,"snippet",raw[max(0,i-270):i+370][:640],flush=True)
# Only test exact application routes for these six IDs. An HTTP 200 without the
# same role identity is NOT enough to mark a job as validated.
routes=[("N26","https://n26.com/en-eu/careers/positions/7845376/apply","7845376")]
for ident in ["42af5ac2-1c89-44ee-b0eb-bad4124ec2ab",
"6777d9e3-caf3-48e0-93ef-80e39230b1c7",
"34647acd-dc06-4897-a30a-f1cca93abc87",
"ffdf2318-a97f-4a71-93ed-bc3e00ea2f12",
"158b9187-b51d-4674-9409-510565ca8a3b"]:
 routes.append(("REVOLUT",f"https://www.revolut.com/careers/apply/{ident}/",ident))
for label,u,ident in routes:
 try:
  r=requests.get(u,headers=H,timeout=12);s=BeautifulSoup(r.text,"html.parser")
  title=s.title.get_text(" ",strip=True) if s.title else ""
  print("APPLY_PROBE",label,ident,r.status_code,r.url,"title",title[:100],
        "id_present",ident in r.text,"forms",len(s.select("form")),
        "inputs",len(s.select("input")),"buttons",[(x.get_text(" ",strip=True) or x.get("value",""))[:55] for x in s.select("button,input[type=submit]")][-8:],
        "closed_marker",bool(re.search(r"no longer available|position has been filled|applications closed|expired",r.text,re.I)),flush=True)
 except Exception as e:print("APPLY_ERROR",label,ident,type(e).__name__,str(e)[:180],flush=True)
