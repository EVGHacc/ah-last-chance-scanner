"""Command line: ``python -m ah_scanner.cli auth-check``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ah_scanner import auth, client, notify, slots, storage

EXIT_OK, EXIT_REAUTH, EXIT_TRANSIENT, EXIT_SCAN_INVALID, EXIT_NOTIFY_FAILED = 0, 2, 3, 4, 5


def auth_check(state: Path, write: bool, post: auth.PostFn = auth.http_post) -> int:
    secret = os.getenv("AH_REFRESH_TOKEN", "")
    try:
        session = auth.refresh_session(secret, state, post=post)
    except auth.AuthError as exc:
        print(f"AUTH_CHECK_FAILED code={exc.code} http={exc.status}")
        return EXIT_REAUTH if exc.code == "AUTH_REAUTH_REQUIRED" else EXIT_TRANSIENT
    persisted = auth.persist_rotation(session, secret, state) if write else False
    print(f"AUTH_CHECK_OK rotated={session.rotated} persisted={persisted}")
    return EXIT_OK


def scan(
    scheduled_raw: str,
    state: Path,
    data_root: Path,
    post: auth.PostFn = auth.http_post,
    graphql: client.GraphqlFn = client.http_graphql,
    now: Callable[[], datetime] = lambda: datetime.now(slots.TZ),
    send: notify.MailFn | None = None,
) -> int:
    """Voer één scan uit en sla het resultaat op. Exitcode != 0 bij elke niet-geldige scan."""
    try:
        scheduled = slots.validate_slot(slots.parse_scheduled_at(scheduled_raw))
    except ValueError as exc:
        print(f"SCAN_REJECTED reason={exc}")
        return EXIT_SCAN_INVALID
    secret = os.getenv("AH_REFRESH_TOKEN", "")

    def get_token(_force: bool) -> str:
        session = auth.refresh_session(secret, state, post=post)
        auth.persist_rotation(session, secret, state)  # rotatie direct bewaren
        return session.access_token

    started = now()
    result = client.run_scan(scheduled, started, get_token, now, graphql)
    written = storage.append_scan(data_root, scheduled, result)
    print(
        f"SCAN status={result.status} late={result.late} delay={result.delay_seconds}s "
        f"stores_ok={sum(s.fetched for s in result.stores)}/{len(result.stores)} written={written}"
    )
    mail = _notify(result, scheduled, data_root, send)
    print(f"NOTIFY {mail}")
    if not result.valid:
        return EXIT_SCAN_INVALID
    return EXIT_NOTIFY_FAILED if mail == "failed" else EXIT_OK


def _notify(result, scheduled, data_root: Path, send: notify.MailFn | None) -> str:
    api_key = os.getenv("RESEND_API_KEY", "")
    sender, to = os.getenv("AH_MAIL_FROM", ""), os.getenv("AH_MAIL_TO", "")
    if send is None:
        if not (api_key and sender and to):
            return "failed" if result.stores and any(s.meat70 for s in result.stores) else "none"
        send = notify.resend_send(api_key)
    return notify.notify(result, scheduled.date(), data_root, send, sender, to)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ah_scanner")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("auth-check", help="Test de refresh-token (geen scan)")
    check.add_argument("--state", type=Path, default=Path("data/auth_state.enc"))
    check.add_argument("--write-state", action="store_true")
    scan_cmd = sub.add_parser("scan", help="Voer één scan uit en schrijf naar --data-root")
    scan_cmd.add_argument("--scheduled-at", required=True)
    scan_cmd.add_argument("--state", type=Path, required=True)
    scan_cmd.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "scan":
        return scan(args.scheduled_at, args.state, args.data_root)
    return auth_check(args.state, args.write_state)


if __name__ == "__main__":
    sys.exit(main())
