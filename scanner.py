# AH Laatste Kans scanner
import json, os, urllib.request, urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
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
    refresh=os.getenv('AH_REFRESH_TOKEN','').strip()
    if refresh:
        s,d=post('/mobile-auth/v1/auth/token/refresh',{'clientId':CLIENT_ID,'refreshToken':refresh})
        if s==200 and d.get('access_token'):
            print('AUTH_MODE=user-refresh')
            return d['access_token'],'user-refresh'
        raise RuntimeError(f'USER_REFRESH_FAILED HTTP {s}: {str(d)[:180]}')
    raise RuntimeError('AH_REFRESH_TOKEN ontbreekt; anonymous fallback is bewust uitgeschakeld')

def make_items(rows, category):
    selected=[x for x in rows if str(x.get('categoryTitle','')).strip().lower()==category.lower()]
    items=[]
    for x in selected:
        m=x.get('markdown') or {}; p=x.get('product') or {}; bp=x.get('bargainPrice') or {}
        items.append({'productId':p.get('id'),'title':p.get('title',''),'brand':p.get('brand',''),'size':p.get('salesUnitSize',''),'category':str(x.get('categoryTitle','')),'discountPct':m.get('markdownPercentage',0) or 0,'stock':x.get('stock',0) or 0,'priceWas':bp.get('priceWas'),'priceNow':bp.get('priceNow'),'markdownExpirationDate':m.get('markdownExpirationDate')})
    return items

def slot_info(now):
    minute=(now.minute//5)*5
    scheduled=now.replace(minute=minute,second=0,microsecond=0)
    delay=max(0,int((now-scheduled).total_seconds()))
    return scheduled, scheduled.strftime('%H:%M'), delay

def main():
    started=datetime.now(TZ)
    scheduled,slot,delay=slot_info(started)
    date=scheduled.strftime('%Y-%m-%d')
    stores=[]
    try:
        t,auth_mode=token()
        for sid,name in STORES:
            s,d=post('/graphql',{'query':QUERY,'variables':{'storeId':str(sid)}},t)
            if s!=200 or d.get('errors'):
                stores.append({'storeId':sid,'store':name,'fetched':False,'totalBargainItems':0,'meatItems':0,'meat70Items':0,'meat70Stock':0,'bakeryItems':0,'bakery70Items':0,'bakery70Stock':0,'items':[],'bakery':[],'error':f'HTTP {s}: {d}'[:350]}); continue
            rows=d.get('data',{}).get('bargainItems') or []
            meat=make_items(rows,'Vlees'); bakery=make_items(rows,'Bakkerij')
            m70=[x for x in meat if float(x['discountPct'])>=70]; b70=[x for x in bakery if float(x['discountPct'])>=70]
            stores.append({'storeId':sid,'store':name,'fetched':True,'totalBargainItems':len(rows),'meatItems':len(meat),'meat70Items':len(m70),'meat70Stock':sum(float(x['stock']) for x in m70),'bakeryItems':len(bakery),'bakery70Items':len(b70),'bakery70Stock':sum(float(x['stock']) for x in b70),'items':meat,'bakery':bakery})
    except Exception as e:
        auth_mode='user-refresh'
        stores=[{'storeId':sid,'store':name,'fetched':False,'totalBargainItems':0,'meatItems':0,'meat70Items':0,'meat70Stock':0,'bakeryItems':0,'bakery70Items':0,'bakery70Stock':0,'items':[],'bakery':[],'error':str(e)[:350]} for sid,name in STORES]
    fetched=sum(1 for x in stores if x['fetched'])
    if fetched==3: status='OK_ZERO_ROWS' if sum(x['meatItems'] for x in stores)==0 else 'OK'
    elif fetched==0: status='FAILED'
    else: status='INCOMPLETE'
    completed=datetime.now(TZ)
    valid=status in ('OK','OK_ZERO_ROWS') and auth_mode=='user-refresh' and delay<=240
    obs={'schemaVersion':3,'date':date,'weekday':scheduled.strftime('%A'),'scheduledSlot':slot,'scheduledAt':scheduled.isoformat(),'startedAt':started.isoformat(),'completedAt':completed.isoformat(),'checkedAt':completed.isoformat(),'delaySeconds':delay,'status':status,'valid':valid,'official1925':slot=='19:25','authMode':auth_mode,'categories':['Vlees','Bakkerij'],'stores':stores}
    os.makedirs('data',exist_ok=True)
    path=f'data/{date}.jsonl'
    with open(path,'a') as f: f.write(json.dumps(obs,ensure_ascii=False)+'\n')
    with open('data/latest.json','w') as f: json.dump(obs,f,ensure_ascii=False,indent=2)
    print(json.dumps(obs,ensure_ascii=False))
    if not valid: raise SystemExit(2)
if __name__=='__main__': main()
