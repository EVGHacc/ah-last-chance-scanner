#!/usr/bin/env python3
import json
import scanner


def main():
    first_access, first_mode = scanner.token()
    first_source = scanner.LAST_AUTH_SOURCE
    second_access, second_mode = scanner.token()
    second_source = scanner.LAST_AUTH_SOURCE
    stores = [scanner.fetch_store(sid, name, second_access) for sid, name in scanner.STORES]
    result_stores = [{
        'storeId': s['storeId'],
        'store': s['store'],
        'fetched': s['fetched'],
        'totalBargainItems': s['totalBargainItems'],
        'meatItems': s['meatItems'],
        'error': s.get('error'),
    } for s in stores]
    token_reused = first_access == second_access and second_source == 'cache'
    ok = first_mode == second_mode == 'user-refresh' and token_reused and all(s['fetched'] for s in result_stores)
    result = {
        'ok': ok,
        'authMode': second_mode,
        'firstAuthSource': first_source,
        'secondAuthSource': second_source,
        'tokenReused': token_reused,
        'categoriesChecked': ['Vlees'],
        'stores': result_stores,
    }
    print(json.dumps(result, ensure_ascii=False))
    if not ok:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
