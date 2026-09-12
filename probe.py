#!/usr/bin/env python3
import json
from scanner import STORES, QUERY, token, post, make_items


def main():
    access, auth_mode = token()
    stores = []
    for sid, name in STORES:
        status, data = post('/graphql', {'query': QUERY, 'variables': {'storeId': str(sid)}}, access)
        errors = data.get('errors') if isinstance(data, dict) else None
        rows = (data.get('data') or {}).get('bargainItems') if isinstance(data, dict) else None
        rows = rows or []
        meat = make_items(rows, 'Vlees') if status == 200 and not errors else []
        stores.append({
            'storeId': sid,
            'store': name,
            'fetched': status == 200 and not errors,
            'totalBargainItems': len(rows),
            'meatItems': len(meat),
            'error': None if status == 200 and not errors else f'HTTP {status}: {str(data)[:250]}',
        })
    ok = auth_mode == 'user-refresh' and all(s['fetched'] for s in stores)
    result = {'ok': ok, 'authMode': auth_mode, 'categoriesChecked': ['Vlees'], 'stores': stores}
    print(json.dumps(result, ensure_ascii=False))
    if not ok:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
