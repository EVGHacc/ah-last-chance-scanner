"""Bounded, secret-safe recovery for AH refresh-token failures."""
import time

TRANSIENT_HTTP_STATUSES = {0, 408, 425, 429, 500, 502, 503, 504}
DEFAULT_RETRY_DELAYS = (0, 2, 5, 10)


class AuthRefreshError(RuntimeError):
    """Authentication failure with a stable, non-secret diagnostic code."""

    def __init__(self, code, status):
        self.code = code
        self.status = status
        if code == "AUTH_REAUTH_REQUIRED":
            message = "AH rejected the available refresh token; interactive re-authentication is required"
        elif code == "AUTH_REFRESH_RETRY_EXHAUSTED":
            message = "Temporary AH/network failures exhausted the bounded refresh retry budget"
        else:
            message = "AH refresh failed with a non-retryable response"
        super().__init__(f"{code}: {message} (HTTP {status})")


def refresh_access_token(
    refresh_token,
    request,
    latest_refresh_token,
    sleep=None,
    delays=DEFAULT_RETRY_DELAYS,
):
    """Refresh with bounded retries, switching only to newer encrypted state."""
    current = str(refresh_token or "").strip()
    if not current:
        raise AuthRefreshError("AUTH_REAUTH_REQUIRED", 0)
    if not delays:
        raise ValueError("delays must contain at least one bounded attempt")

    sleep_fn = sleep or time.sleep
    attempted_tokens = {current}
    last_status = 0

    for index, delay in enumerate(delays):
        if delay:
            sleep_fn(delay)

        status, payload = request(current)
        last_status = status
        payload = payload if isinstance(payload, dict) else {}

        if status == 200 and str(payload.get("access_token") or "").strip():
            return payload, current

        if status in (400, 401):
            try:
                replacement = str(latest_refresh_token() or "").strip()
            except Exception:
                replacement = ""
            if replacement and replacement not in attempted_tokens and index < len(delays) - 1:
                current = replacement
                attempted_tokens.add(current)
                continue
            raise AuthRefreshError("AUTH_REAUTH_REQUIRED", status)

        if status not in TRANSIENT_HTTP_STATUSES:
            raise AuthRefreshError("AUTH_REFRESH_FAILED", status)

        if index == len(delays) - 1:
            raise AuthRefreshError("AUTH_REFRESH_RETRY_EXHAUSTED", status)

    raise AuthRefreshError("AUTH_REFRESH_RETRY_EXHAUSTED", last_status)
