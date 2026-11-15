"""Command line: ``python -m ah_scanner.cli auth-check``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ah_scanner import auth

EXIT_OK, EXIT_REAUTH, EXIT_TRANSIENT = 0, 2, 3


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ah_scanner")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("auth-check", help="Test de refresh-token (geen scan)")
    check.add_argument("--state", type=Path, default=Path("data/auth_state.enc"))
    check.add_argument("--write-state", action="store_true")
    args = parser.parse_args(argv)
    return auth_check(args.state, args.write_state)


if __name__ == "__main__":
    sys.exit(main())
