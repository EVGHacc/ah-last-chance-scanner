"""Independent read-only classification audit and match report."""
from urllib.parse import urlparse


def source_id(row):
    return str(row["kind"]) + "::" + str(row["name"])


def _identity_set(rows):
    keys = [source_id(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate source identity")
    return set(keys)


def _proven_route(entry):
    for provider, route in (entry.get("platforms") or {}).items():
        if route.get("status") != "PROVEN":
            continue
        url = urlparse(route.get("evidence_url") or "")
        if provider and url.scheme == "https" and url.netloc and route.get("checked_at") and route.get("route_type"):
            return True
    return False


def audit_classification(manifest, provider_map, ledger):
    expected = 113
    if manifest.get("target_count") != expected or ledger.get("target_count") != expected:
        raise ValueError("live denominator must be exactly 113")
    m, p, l = manifest["sources"], provider_map["sources"], ledger["records"]
    if any(len(rows) != expected for rows in (m, p, l)):
        raise ValueError("113 entries required")
    ids = _identity_set(m)
    if _identity_set(p) != ids:
        raise ValueError("provider map identity mismatch")
    ledger_ids = [row.get("source_id") for row in l]
    if len(set(ledger_ids)) != expected or set(ledger_ids) != ids:
        raise ValueError("ledger identity mismatch")
    complete = [row for row in p if _proven_route(row)]
    missing = [source_id(row) for row in p if not _proven_route(row)]
    status_only = [source_id(row) for row in p if not _proven_route(row)
                   and any(route.get("status") == "PROVEN" for route in (row.get("platforms") or {}).values())]
    certified = sum(row.get("certification") == "CERTIFIED" for row in l)
    if ledger.get("certified_coverage") != certified:
        raise ValueError("ledger certified count mismatch")
    return {"denominator":113, "identity_set_equal":True, "evidence_complete":len(complete),
            "unclassified":missing, "proven_but_incomplete":status_only,
            "certified":certified, "certification_target":37,
            "certification_gap":max(0,37-certified)}
