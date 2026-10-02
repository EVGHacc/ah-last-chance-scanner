from urllib.request import Request, urlopen
import json

class TransportError(RuntimeError):
    pass

def fetch_json(url, timeout=20, max_bytes=12000000):
    request=Request(url,headers={"Accept":"application/json","User-Agent":"vacancy-scanner-v4/1"})
    try:
        with urlopen(request,timeout=timeout) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise TransportError("invalid HTTP response")
            raw=response.read(max_bytes+1)
    except Exception as exc:
        if isinstance(exc,TransportError): raise
        raise TransportError("network failure") from exc
    if len(raw)>max_bytes: raise TransportError("response exceeds byte cap")
    try: return json.loads(raw)
    except Exception as exc: raise TransportError("invalid JSON") from exc
