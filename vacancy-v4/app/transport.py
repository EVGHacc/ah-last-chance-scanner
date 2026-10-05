from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import time

class TransportError(RuntimeError):
    pass

_TRANSIENT_HTTP={408,425,429,500,502,503,504}

def _read(url, accept, timeout, max_bytes, retries=2, backoff=0.5):
    request=Request(url,headers={"Accept":accept,"User-Agent":"vacancy-scanner-v4/1"})
    for attempt in range(retries+1):
        try:
            with urlopen(request,timeout=timeout) as response:
                if response.status != 200:
                    raise TransportError("invalid HTTP response")
                raw=response.read(max_bytes+1)
                content_type=response.headers.get_content_type()
            break
        except HTTPError as exc:
            if exc.code not in _TRANSIENT_HTTP or attempt>=retries:
                raise TransportError("network failure") from exc
            time.sleep(backoff*(2**attempt))
        except (URLError, TimeoutError, ConnectionError) as exc:
            if attempt>=retries:
                raise TransportError("network failure") from exc
            time.sleep(backoff*(2**attempt))
        except Exception as exc:
            if isinstance(exc,TransportError): raise
            raise TransportError("network failure") from exc
    if len(raw)>max_bytes: raise TransportError("response exceeds byte cap")
    return raw,content_type

def fetch_json(url, timeout=20, max_bytes=12000000, retries=2, backoff=0.5):
    raw,content_type=_read(url,"application/json",timeout,max_bytes,retries=retries,backoff=backoff)
    if content_type != "application/json":
        raise TransportError("invalid HTTP response")
    try: return json.loads(raw)
    except Exception as exc: raise TransportError("invalid JSON") from exc

def fetch_text(url, timeout=20, max_bytes=16000000, retries=2, backoff=0.5):
    raw,content_type=_read(url,"text/html,application/xhtml+xml",timeout,max_bytes,retries=retries,backoff=backoff)
    if content_type not in {"text/html","application/xhtml+xml"}:
        raise TransportError("invalid HTML response")
    try: return raw.decode("utf-8")
    except Exception as exc: raise TransportError("invalid HTML encoding") from exc
