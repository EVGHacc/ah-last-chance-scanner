# AH Laatste Kans scanner
import json, os, time, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

TZ=ZoneInfo('Europe/Amsterdam')
STORES=[(1463,'AH Blekersvaartweg'),(1348,'AH Zandvoortselaan'),(1135,'AH Casablancastraat')]
BASE='https://api.ah.nl'
CLIENT_ID='appie-ios'
HEADERS={'User-Agent':'Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)','x-client-name':CLIENT_ID,'x-client-version':'9.28','x-application':'AHWEBSHOP','Accept':'application/json','Content-Type':'application/json'}
QUERY='''query BargainItems($storeId: String!) { bargainItems(storeId: $storeId) { product { id title brand salesUnitSize } categoryTitle markdown { markdownType markdownExpirationDate markdownPercentage } stock bargainPrice { priceWas priceNow } } }'''
START=17*60+30
END=22*60+30
TRANSIENT_HTTP={429,500,502,503,504}


def post(path,body,token=None,attempts=2):
    h=dict(HEADERS)
    if token: h['Authorization']='Bearer '+token
    payload=json.dumps(body).encode()
    last_status=0
    last_data={'error':'request failed'}
    for attempt in range(1,attempts+1):
        req=urllib.request.Request(BASE+path,data=payload,headers=h,method='POST')
        try:
            with urllib.request.urlopen(req,timeout=20) as r:
                return r.status,json.loads(r.read())
        except urllib.error.HTTPError as e:
            last_status=e.code
            last_data={'error':e.read().decode(errors='replace')[:300]}
            if e.code not in TRANSIENT_HTTP or attempt==attempts:
                return last_status,last_data
        except (urllib.error.URLError,TimeoutError,OSError) as e:
            last_status=0
            last_data={'error':f'{type(e).__name__}: {e}'[:300]}
            if attempt==attempts:
                return last_status,last_data
        time.sleep(attempt)
    return last_status,last_data


def token():
    refresh=os.getenv('AH_REFRESH_TOKEN','').strip()
    if not refresh: raise RuntimeError('AH_REFRESH_TOKEN ontbreekt; anonymous fallback is uitgeschakeld')
    s,d=post('/mobile-auth/v1/auth/token/refresh',{'clientId':CLIENT_ID,'refreshToken':refresh},attempts=3)
    if s==200 and d.get('access_token'): return d['access_token'],'user-refresh'
    raise RuntimeError(f'USER_REFRESH_FAILED HTTP {s}: {str(d)[:180]}')


def make_items(rows,category):
    out=[]
    for x in rows:
        if str(x.get('categoryTitle','')).strip().lower()!=category.lower(): continue
        m=x.get('markdown') or {}; p=x.get('product') or {}; bp=x.get('bargainPrice') or {}
        out.append({'productId':p.get('id'),'title':p.get('title',''),'brand':p.get('brand',''),'size':p.get('salesUnitSize',''),'category':str(x.get('categoryTitle','')),'discountPct':m.get('markdownPercentage',0) or 0,'stock':x.get('stock',0) or 0,'priceWas':bp.get('priceWas'),'priceNow':bp.get('priceNow'),'markdownExpirationDate':m.get('markdownExpirationDate')})
    return out


def parse_raw_schedule(started):
    raw=os.getenv('SCHEDULED_AT','').strip()
    if raw:
        scheduled=datetime.fromisoformat(raw.replace('Z','+00:00')).astimezone(TZ)
    else:
        scheduled=started.replace(second=0,microsecond=0)
    mins=scheduled.hour*60+scheduled.minute
    if not (START<=mins<=END): raise RuntimeError(f'scheduled time buiten scanvenster: {scheduled.isoformat()}')
    return scheduled


def canonical_slot(scheduled):
    minute=(scheduled.minute//5)*5
    canonical=scheduled.replace(minute=minute,second=0,microsecond=0)
    return canonical,canonical.strftime('%H:%M')


def fetch_store(sid,name,access):
    status=0; data={}
    for attempt in range(1,3):
        status,data=post('/graphql',{'query':QUERY,'variables':{'storeId':str(sid)}},access,attempts=2)
        if status==200 and not data.get('errors'):
            rows=(data.get('data') or {}).get('bargainItems') or []
            meat=make_items(rows,'Vlees'); bakery=make_items(rows,'Bakkerij')
            m70=[x for x in meat if float(x['discountPct'])>=70]; b70=[x for x in bakery if float(x['discountPct'])>=70]
            return {'storeId':sid,'store':name,'fetched':True,'totalBargainItems':len(rows),'meatItems':len(meat),'meat70Items':len(m70),'meat70Stock':sum(float(x['stock']) for x in m70),'bakeryItems':len(bakery),'bakery70Items':len(b70),'bakery70Stock':sum(float(x['stock']) for x in b70),'items':meat,'bakery':bakery}
        if attempt<2: time.sleep(1)
    return {'storeId':sid,'store':name,'fetched':False,'totalBargainItems':0,'meatItems':0,'meat70Items':0,'meat70Stock':0,'bakeryItems':0,'bakery70Items':0,'bakery70Stock':0,'items':[],'bakery':[],'error':f'HTTP {status}: {data}'[:350]}


def main():
    started=datetime.now(TZ)
    raw_scheduled=parse_raw_schedule(started)
    canonical,slot=canonical_slot(raw_scheduled)
    date=canonical.strftime('%Y-%m-%d')
    raw_delay=max(0,int((started-raw_scheduled).total_seconds()))
    canonical_delay=max(0,int((started-canonical).total_seconds()))
    stores=[]
    auth_mode='user-refresh-failed'
    try:
        access,auth_mode=token()
        stores=[fetch_store(sid,name,access) for sid,name in STORES]
    except Exception as e:
        stores=[{'storeId':sid,'store':name,'fetched':False,'totalBargainItems':0,'meatItems':0,'meat70Items':0,'meat70Stock':0,'bakeryItems':0,'bakery70Items':0,'bakery70Stock':0,'items':[],'bakery':[],'error':str(e)[:350]} for sid,name in STORES]
    fetched=sum(1 for x in stores if x['fetched'])
    status=('OK_ZERO_ROWS' if sum(x['meatItems'] for x in stores)==0 else 'OK') if fetched==3 else ('FAILED' if fetched==0 else 'INCOMPLETE')
    completed=datetime.now(TZ)
    # Raw observations are judged against their own trigger time. Canonical timing
    # quality is enforced separately by scripts/persist.py for exact 5-minute runs.
    valid=status in ('OK','OK_ZERO_ROWS') and auth_mode=='user-refresh' and raw_delay<=240
    obs={'schemaVersion':4,'date':date,'weekday':canonical.strftime('%A'),'scheduledSlot':slot,'scheduledAt':canonical.isoformat(),'rawScheduledSlot':raw_scheduled.strftime('%H:%M'),'rawScheduledAt':raw_scheduled.isoformat(),'startedAt':started.isoformat(),'completedAt':completed.isoformat(),'checkedAt':completed.isoformat(),'delaySeconds':canonical_delay,'rawDelaySeconds':raw_delay,'status':status,'valid':valid,'official1925':slot=='19:25' and raw_scheduled.strftime('%H:%M')=='19:25','authMode':auth_mode,'categories':['Vlees','Bakkerij'],'stores':stores}
    os.makedirs('data',exist_ok=True)
    with open('data/latest.json','w',encoding='utf-8') as f: json.dump(obs,f,ensure_ascii=False,indent=2)
    print(json.dumps(obs,ensure_ascii=False))
    if not valid: raise SystemExit(2)

if __name__=='__main__': main()
