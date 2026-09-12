# AH Laatste Kans scanner
import json, os, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

STORES=[(1463,'AH Blekersvaartweg'),(1348,'AH Zandvoortselaan'),(1135,'AH Casablancastraat')]
BASE='https://api.ah.nl'
CLIENT_ID='appie-ios'
HEADERS={'User-Agent':'Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)','x-client-name':CLIENT_ID,'x-client-version':'9.28','x-application':'AHWEBSHOP','Accept':'application/json','Content-Type':'application/json'}
QUERY='''query BargainItems($storeId: String!) { bargainItems(storeId: $storeId) { product { id title brand salesUnitSize } categoryTitle markdown { markdownType markdownExpirationDate markdownPercentage } stock bargainPrice { priceWas priceNow } } }'''

def post(path,body,token=None):
    h=dict(HEADERS)
    if token: h['Authorization']='Bearer '+token
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode(),headers=h,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=20) as r: return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code,{'error':e.read().decode(errors='replace')[:300]}

def token():
    s,d=post('/mobile-auth/v1/auth/token/anonymous',{'clientId':CLIENT_ID})
    if s!=200 or not d.get('access_token'): raise RuntimeError(f'ANON AUTH HTTP {s}: {d}')
    return d['access_token']

def main():
    now=datetime.now(ZoneInfo('Europe/Amsterdam')); slot=now.strftime('%H:%M'); date=now.strftime('%Y-%m-%d')
    t=token(); stores=[]
    for sid,name in STORES:
        s,d=post('/graphql',{'query':QUERY,'variables':{'storeId':str(sid)}},t)
        if s!=200 or d.get('errors'):
            stores.append({'storeId':sid,'store':name,'fetched':False,'error':f'HTTP {s}: {d}'[:350]}); continue
        rows=d.get('data',{}).get('bargainItems') or []
        meat=[x for x in rows if str(x.get('categoryTitle','')).strip().lower()=='vlees']
        items=[]
        for x in meat:
            m=x.get('markdown') or {}; p=x.get('product') or {}; bp=x.get('bargainPrice') or {}
            items.append({'productId':p.get('id'),'title':p.get('title',''),'brand':p.get('brand',''),'size':p.get('salesUnitSize',''),'discountPct':m.get('markdownPercentage',0) or 0,'stock':x.get('stock',0) or 0,'priceWas':bp.get('priceWas'),'priceNow':bp.get('priceNow'),'markdownExpirationDate':m.get('markdownExpirationDate')})
        m70=[x for x in items if float(x['discountPct'])>=70]
        stores.append({'storeId':sid,'store':name,'fetched':True,'totalBargainItems':len(rows),'meatItems':len(items),'meat70Items':len(m70),'meat70Stock':sum(float(x['stock']) for x in m70),'items':items})
    obs={'date':date,'scheduledSlot':slot,'checkedAt':now.isoformat(),'status':'OK' if all(x['fetched'] for x in stores) else 'INCOMPLETE','authMode':'anonymous','stores':stores}
    os.makedirs('data',exist_ok=True)
    path=f'data/{date}.jsonl'
    with open(path,'a') as f: f.write(json.dumps(obs,ensure_ascii=False)+'\n')
    with open('data/latest.json','w') as f: json.dump(obs,f,ensure_ascii=False,indent=2)
    print(json.dumps(obs,ensure_ascii=False))
    if obs['status'] != 'OK':
        raise SystemExit(2)
if __name__=='__main__': main()
