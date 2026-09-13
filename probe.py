#!/usr/bin/env python3
import json
from scanner import STORES, token, fetch_store


def main():
    access, auth_mode = token()
    stores = [fetch_store(sid, name, access) for sid, name in STORES]
    result_stores = [{
        'storeId': s['storeId'],
        'store': s['store'],
        'fetched': s['fetched'],
        'totalBargainItems': s['totalBargainItems'],
        'meatItems': s['meatItems'],
        'error': s.get('error'),
    } for s in stores]
    ok = auth_mode == 'user-refresh' and all(s['fetched'] for s in result_stores)
    result = {'ok': ok, 'authMode': auth_mode, 'categoriesChecked': ['Vlees'], 'stores': result_stores}
    print(json.dumps(result, ensure_ascii=False))
    if not ok:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
