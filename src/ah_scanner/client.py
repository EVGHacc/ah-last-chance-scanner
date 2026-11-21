"""GraphQL-client voor AH 'bargainItems' en samenstellen van een scanresultaat.

Auth en HTTP zijn injecteerbaar zodat alles zonder netwerk testbaar is.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime

from ah_scanner import auth, filters, slots
from ah_scanner.models import (
    FAILED,
    INCOMPLETE,
    OK,
    OK_ZERO_ROWS,
    STORES,
    ScanResult,
    StoreResult,
)

QUERY = (
    "query BargainItems($storeId: String!) { bargainItems(storeId: $storeId) { "
    "product { id title brand salesUnitSize } categoryTitle "
    "markdown { markdownType markdownExpirationDate markdownPercentage } stock "
    "bargainPrice { priceWas priceNow } } }"
)

DETAIL_KEY = "_detail"
GraphqlFn = Callable[[str, str], tuple[int, dict]]  # (store_id, access_token) -> (status, data)
TokenFn = Callable[[bool], str]  # (force_refresh) -> access_token


def http_query(query: str, variables: dict, access: str) -> tuple[int, dict]:
    """Eén GraphQL-aanroep; geeft (HTTP-status, JSON) terug, (0, {}) bij een netwerkfout."""
    headers = dict(auth.HEADERS, Authorization=f"Bearer {access}")
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(auth.BASE_URL + "/graphql", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {DETAIL_KEY: _clean(_read_body(exc))}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, {}


def _read_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read(200).decode("utf-8", "replace")
    except Exception:
        return ""


def _clean(text: str) -> str:
    """Korte, veilige foutdetail: alleen letters, cijfers en een paar tekens, max 60 tekens."""
    cleaned = re.sub(r"[^A-Za-z0-9 _.:/-]+", " ", text or "")
    return re.sub(r"\s+", " ", cleaned).strip()[:60]


def error_detail(data: dict) -> str:
    """Reden van een mislukte aanroep: GraphQL-foutcode of -tekst, of het begin van een foutbody."""
    if detail := data.get(DETAIL_KEY):
        return str(detail)
    errors = data.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        first = errors[0]
        ext = first.get("extensions") if isinstance(first.get("extensions"), dict) else {}
        return _clean(str(ext.get("code") or first.get("message") or ""))
    return ""


def http_graphql(store_id: str, access: str) -> tuple[int, dict]:
    return http_query(QUERY, {"storeId": store_id}, access)


def _failed(store_id: int, name: str, code: str) -> StoreResult:
    return StoreResult(store_id, name, fetched=False, error=code)


def fetch_store(
    store_id: int,
    name: str,
    get_token: TokenFn,
    graphql: GraphqlFn = http_graphql,
    attempts: int = 2,
) -> StoreResult:
    """Haal één winkel op. Eén 401 -> één token-refresh en opnieuw; tweede 401 = auth-fout."""
    refreshed = False
    try:
        access = get_token(False)
    except auth.AuthError as exc:
        return _failed(store_id, name, exc.code)
    tries = 0
    while tries < attempts:
        status, data = graphql(str(store_id), access)
        if status == 401:
            if refreshed:
                return _failed(store_id, name, "AUTH_REAUTH_REQUIRED")
            refreshed = True
            try:
                access = get_token(True)
            except auth.AuthError as exc:
                return _failed(store_id, name, exc.code)
            continue  # de refresh-ronde telt niet als poging
        tries += 1
        if status == 200 and not data.get("errors"):
            rows = (data.get("data") or {}).get("bargainItems") or []
            meat = filters.meat_items(rows)
            return StoreResult(
                store_id,
                name,
                fetched=True,
                total_items=len(rows),
                meat_items=tuple(meat),
                meat70=tuple(filters.meat70(meat)),
            )
    code = f"UPSTREAM_HTTP_{status or 'ERROR'}"
    detail = error_detail(data)
    return _failed(store_id, name, f"{code}: {detail}" if detail else code)


def overall_status(stores: list[StoreResult]) -> str:
    fetched = [s for s in stores if s.fetched]
    if not fetched:
        return FAILED
    if len(fetched) < len(stores):
        return INCOMPLETE
    return OK if any(s.meat_items for s in stores) else OK_ZERO_ROWS


def run_scan(
    scheduled: datetime,
    started: datetime,
    get_token: TokenFn,
    now: Callable[[], datetime],
    graphql: GraphqlFn = http_graphql,
) -> ScanResult:
    """Scan alle winkels. Tijdstempels zijn echt; een late scan wordt nooit teruggedateerd."""
    results = [fetch_store(sid, name, get_token, graphql) for sid, name in STORES]
    delay = slots.delay_seconds(scheduled, started)
    return ScanResult(
        scheduled_at=scheduled.isoformat(),
        started_at=started.isoformat(),
        completed_at=now().isoformat(),
        delay_seconds=delay,
        late=slots.is_late(delay),
        status=overall_status(results),
        stores=tuple(results),
    )
