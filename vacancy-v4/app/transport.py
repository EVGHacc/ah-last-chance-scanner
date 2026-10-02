from urllib.request import Request, urlopen
import json

class TransportError(RuntimeError):
    pass

def _read(url, accept, timeout, max_bytes):
    request=Request(url,headers={"Accept":accept,"User-Agent":"vacancy-scanner-v4/1"})
    try:
        with urlopen(request,timeout=timeout) as response:
            if response.status != 200:
                raise TransportError("invalid HTTP response")
            raw=response.read(max_bytes+1)
            content_type=response.headers.get_content_type()
    except Exception as exc:
        if isinstance(exc,TransportError): raise
        raise TransportError("network failure") from exc
    if len(raw)>max_bytes: raise TransportError("response exceeds byte cap")
    return raw,content_type

def fetch_json(url, timeout=20, max_bytes=12000000):
    raw,content_type=_read(url,"application/json",timeout,max_bytes)
    if content_type != "application/json":
        raise TransportError("invalid HTTP response")
    try: return json.loads(raw)
    except Exception as exc: raise TransportError("invalid JSON") from exc

def fetch_text(url, timeout=20, max_bytes=16000000):
    raw,content_type=_read(url,"text/html,application/xhtml+xml",timeout,max_bytes)
    if content_type not in {"text/html","application/xhtml+xml"}:
        raise TransportError("invalid HTML response")
    try: return raw.decode("utf-8")
    except Exception as exc: raise TransportError("invalid HTML encoding") from exc
