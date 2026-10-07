import json
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlparse
from .providers.personio import parse_inventory
from .registry import load_sources
from .transport import _read,fetch_text

CONFIG=Path(__file__).resolve().parents[1]/'config/personio_sources.json'

def xml(url):
    raw,kind=_read(url,'application/xml,text/xml',20,16000000)
    if kind not in ('text/xml','application/xml'): raise ValueError('not XML')
    return raw.decode()

def run_batch(fetcher=None,config_path=CONFIG):
    rows=json.loads(Path(config_path).read_text())['sources']
    known={s.name for s in load_sources()}
    out=[]
    for row in rows:
        host=urlparse(row['board_url']).hostname
        if row['name'] not in known or not host or not host.endswith(('.jobs.personio.com','.jobs.personio.de')) or urlparse(row['feed_url']).netloc!=host:
            raise ValueError('untrusted source')
        t=datetime.now(timezone.utc).isoformat()
        try:
            jobs=parse_inventory((fetcher or xml)(row['feed_url']),row['board_url'],fetch_text)
            out.append(dict(name=row['name'],coverage='verified_complete',unique_jobs=len(jobs),jobs=jobs,checked_at=t,error=None))
        except Exception as e:
            out.append(dict(name=row['name'],coverage='unproven',unique_jobs=0,jobs=[],checked_at=t,error=str(e)))
    ok=sum(x['coverage']=='verified_complete' for x in out)
    return dict(schema_version=1,provider='personio',configured_sources=len(out),verified_complete=ok,failed=len(out)-ok,sources=out)
