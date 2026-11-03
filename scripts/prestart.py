#!/usr/bin/env python3
"""Non-invasive AH prestart checks; deliberately performs no auth/network probe."""
import os


def validate_preflight(env=None):
    """Require the configured refresh-token secret without reading its value."""
    values = os.environ if env is None else env
    token = values.get("AH_REFRESH_TOKEN")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("PRESTART BLOCKER: AH_REFRESH_TOKEN missing")
    return True


def main():
    validate_preflight()
    print("PRESTART READY: refresh-token secret is configured; no live-auth probe performed")


if __name__ == "__main__":
    main()
