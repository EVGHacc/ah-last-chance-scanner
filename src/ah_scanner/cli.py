"""Command line: ``python -m ah_scanner.cli auth-check``."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ah_scanner import analyze, auth, client, enrich, export, notify, slots, storage

EXIT_OK, EXIT_REAUTH, EXIT_TRANSIENT, EXIT_SCAN_INVALID, EXIT_NOTIFY_FAILED = 0, 2, 3, 4, 5


def _crypto_unavailable() -> bool:
    try:
        auth.require_cryptography()
    except ImportError as exc:
        print(f"CRYPTOGRAPHY_UNAVAILABLE type={type(exc).__name__}")
        return True
    return False


def auth_check(state: Path, write: bool, post: auth.PostFn = auth.http_post) -> int:
    if (
        write and _crypto_unavailable()
    ):  # voor de refresh, anders gaat een geroteerde token verloren
        return EXIT_TRANSIENT
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
    query: enrich.QueryFn | None = None,
) -> int:
    """Voer één scan uit en sla het resultaat op. Exitcode != 0 bij elke niet-geldige scan."""
    if _crypto_unavailable():  # voor de refresh, anders gaat een geroteerde token verloren
        return EXIT_SCAN_INVALID
    try:
        scheduled = slots.validate_slot(slots.parse_scheduled_at(scheduled_raw))
    except ValueError as exc:
        print(f"SCAN_REJECTED reason={exc}")
        return EXIT_SCAN_INVALID
    secret = os.getenv("AH_REFRESH_TOKEN", "")

    cache: dict[str, str] = {}

    def get_token(force: bool) -> str:
        if not force and "access" not in cache:
            reused = auth.cached_access(state, secret)  # minder verversen = minder rotaties
            if reused:
                cache["access"] = reused
                print("AUTH_ACCESS reused=true")
        if force or "access" not in cache:  # anders één refresh per scan, plus bij een 401
            session = auth.refresh_session(secret, state, post=post)
            auth.persist_rotation(session, secret, state)  # rotatie direct bewaren
            cache["access"] = session.access_token
            left = (
                "unknown"
                if session.expires_at is None
                else f"{session.expires_at - time.time():.0f}"
            )
            print(f"AUTH_ACCESS reused=false expires_in_s={left}")
        return cache["access"]

    started = now()
    result = client.run_scan(scheduled, started, get_token, now, graphql)
    written = storage.append_scan(data_root, scheduled, result)
    print(
        f"SCAN status={result.status} late={result.late} delay={result.delay_seconds}s "
        f"stores_ok={sum(s.fetched for s in result.stores)}/{len(result.stores)} written={written}"
    )

    def run_query(text: str, variables: dict) -> tuple[int, dict]:
        try:
            return client.http_query(text, variables, get_token(False))
        except auth.AuthError:
            return 0, {}

    mail = _notify(result, scheduled, data_root, send, query or run_query)
    print(f"NOTIFY {mail}")
    if not result.valid:
        return EXIT_SCAN_INVALID
    return EXIT_NOTIFY_FAILED if mail == "failed" else EXIT_OK


def _notify(
    result, scheduled, data_root: Path, send: notify.MailFn | None, query: enrich.QueryFn
) -> str:
    api_key = os.getenv("RESEND_API_KEY", "")
    sender, to = os.getenv("AH_MAIL_FROM", ""), os.getenv("AH_MAIL_TO", "")
    if send is None:
        if not (api_key and sender and to):
            return "failed" if result.stores and any(s.meat70 for s in result.stores) else "none"
        send = notify.resend_send(api_key)

    def enrich_new(items: list) -> dict:
        return enrich.enrich_items(items, query, data_root)

    return notify.notify(result, scheduled.date(), data_root, send, sender, to, enrich_new)


def report(data_root: Path, out: Path, mail: bool, send: notify.MailFn | None = None) -> int:
    """Maak het weekrapport, schrijf ``reports/<week>.md`` en mail het (optioneel)."""
    data = analyze.report(analyze.build(data_root))
    label = analyze.week_label(data)
    markdown = analyze.render_markdown(data)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{label}.md").write_text(markdown, encoding="utf-8")
    print(f"REPORT week={label} days={data['quality']['days']} offers={data['quality']['offers']}")
    if not mail:
        return EXIT_OK
    sender, to = os.getenv("AH_MAIL_FROM", ""), os.getenv("AH_MAIL_TO", "")
    api_key = os.getenv("RESEND_API_KEY", "")
    if send is None:
        if not (api_key and sender and to):
            print("REPORT_MAIL failed reason=missing-config")
            return EXIT_NOTIFY_FAILED
        send = notify.resend_send(api_key)
    payload = {
        "from": sender,
        "to": [to],
        "subject": f"AH Laatste Kans weekrapport {label}",
        "text": markdown,
        "html": analyze.render_html(data),
    }
    ok = send(payload)
    print(f"REPORT_MAIL {'sent' if ok else 'failed'}")
    return EXIT_OK if ok else EXIT_NOTIFY_FAILED


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ah_scanner")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("auth-check", help="Test de refresh-token (geen scan)")
    check.add_argument("--state", type=Path, default=Path("data/auth_state.enc"))
    check.add_argument("--write-state", action="store_true")
    export_cmd = sub.add_parser("export", help="Maak CSV-bestanden voor analyse (v1 en v2)")
    export_cmd.add_argument("--data-root", type=Path, default=Path("."))
    export_cmd.add_argument("--out", type=Path, required=True)
    export_cmd.add_argument("--combined", action="store_true", help="ook scans_all/items_all.csv")
    report_cmd = sub.add_parser("report", help="Weekrapport met trends (v1 en v2)")
    report_cmd.add_argument("--data-root", type=Path, default=Path("."))
    report_cmd.add_argument("--out", type=Path, required=True)
    report_cmd.add_argument("--mail", action="store_true", help="mail het rapport via Resend")
    scan_cmd = sub.add_parser("scan", help="Voer één scan uit en schrijf naar --data-root")
    scan_cmd.add_argument("--scheduled-at", required=True)
    scan_cmd.add_argument("--state", type=Path, required=True)
    scan_cmd.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "report":
        return report(args.data_root, args.out, args.mail)
    if args.command == "export":
        stats = export.export_all(args.data_root, args.out, args.combined)
        print(
            f"EXPORT days={stats['days']} scan_rows={stats['scan_rows']} "
            f"item_rows={stats['item_rows']} skipped={stats['skipped']}"
        )
        return EXIT_OK
    if args.command == "scan":
        return scan(args.scheduled_at, args.state, args.data_root)
    return auth_check(args.state, args.write_state)


if __name__ == "__main__":
    sys.exit(main())
