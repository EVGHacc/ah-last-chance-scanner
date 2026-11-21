from datetime import datetime, timedelta

from ah_scanner import auth, client, slots
from ah_scanner.models import FAILED, INCOMPLETE, OK, OK_ZERO_ROWS, STORES

from .test_filters_slots import row


def ok_payload(*rows):
    return 200, {"data": {"bargainItems": list(rows)}}


def tokens():
    calls = []

    def get(force):
        calls.append(force)
        return "fresh" if force else "old"

    get.calls = calls
    return get


def test_401_dan_refresh_dan_succes():
    seen = []

    def gql(store, access):
        seen.append(access)
        return (401, {}) if access == "old" else ok_payload(row(pct=75))

    get = tokens()
    result = client.fetch_store(1, "w", get, gql)
    assert result.fetched and len(result.meat70) == 1
    assert seen == ["old", "fresh"] and get.calls == [False, True]


def test_tweede_401_is_auth_fout():
    result = client.fetch_store(1, "w", tokens(), lambda s, a: (401, {}))
    assert not result.fetched and result.error == "AUTH_REAUTH_REQUIRED"


def test_refresh_mislukt_geeft_stabiele_code():
    def get(force):
        raise auth.AuthError("AUTH_REAUTH_REQUIRED", 401)

    result = client.fetch_store(1, "w", get, lambda s, a: ok_payload())
    assert result.error == "AUTH_REAUTH_REQUIRED"


def test_tijdelijke_fout_begrensd():
    n = []

    def gql(store, access):
        n.append(1)
        return 503, {}

    result = client.fetch_store(1, "w", tokens(), gql, attempts=2)
    assert len(n) == 2 and result.error == "UPSTREAM_HTTP_503"


def test_graphql_errors_zijn_geen_succes():
    result = client.fetch_store(1, "w", tokens(), lambda s, a: (200, {"errors": [{}]}))
    assert not result.fetched


def _scan(gql):
    sched = datetime(2026, 11, 15, 17, 30, tzinfo=slots.TZ)
    started = sched + timedelta(hours=3)
    return client.run_scan(sched, started, tokens(), lambda: started, gql)


def test_ok_en_late_met_echte_tijd():
    scan = _scan(lambda s, a: ok_payload(row(pct=80)))
    assert scan.status == OK and scan.valid and scan.late
    assert scan.started_at != scan.scheduled_at and scan.delay_seconds == 10800
    assert len(scan.stores) == len(STORES) == 5


def test_ok_zero_rows():
    assert _scan(lambda s, a: ok_payload(row("Bakkerij"))).status == OK_ZERO_ROWS


def test_incomplete_bij_uitgevallen_winkel():
    def gql(store, access):
        return (500, {}) if store == "8728" else ok_payload(row())

    scan = _scan(gql)
    assert scan.status == INCOMPLETE and not scan.valid


def test_failed_bij_alle_winkels_uit():
    scan = _scan(lambda s, a: (500, {}))
    assert scan.status == FAILED and not scan.valid


def test_graphql_fout_op_http_200_bewaart_een_korte_veilige_reden():
    payload = (200, {"errors": [{"message": "Rate limit <exceeded>!", "extensions": {}}]})
    result = client.fetch_store(1, "w", tokens(), lambda s, a: payload)
    assert result.error == "UPSTREAM_HTTP_200: Rate limit exceeded"
    coded = (200, {"errors": [{"message": "x", "extensions": {"code": "TOO_MANY_REQUESTS"}}]})
    assert client.fetch_store(1, "w", tokens(), lambda s, a: coded).error.endswith(
        "TOO_MANY_REQUESTS"
    )


def test_foutbody_bij_403_wordt_ingekort_en_zonder_speciale_tekens_bewaard():
    long_body = {client.DETAIL_KEY: client._clean("<html>Access denied " + "x" * 200)}
    result = client.fetch_store(1, "w", tokens(), lambda s, a: (403, long_body))
    assert result.error.startswith("UPSTREAM_HTTP_403: html Access denied")
    assert len(result.error) <= len("UPSTREAM_HTTP_403: ") + 60 and "<" not in result.error


def test_zonder_detail_blijft_de_foutcode_zoals_voorheen():
    assert client.error_detail({}) == "" and client.error_detail({"errors": []}) == ""
    assert client.error_detail({"errors": ["tekst"]}) == ""
    result = client.fetch_store(1, "w", tokens(), lambda s, a: (503, {}))
    assert result.error == "UPSTREAM_HTTP_503"
