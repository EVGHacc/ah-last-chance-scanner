#!/usr/bin/env python3
"""One-command recovery of the AH user refresh token on macOS.

Run from any Terminal folder:
  curl -fsSL https://raw.githubusercontent.com/EVGHacc/ah-last-chance-scanner/main/scripts/recover_ah_auth.py | python3 -

The script opens the official AH login through a localhost reverse proxy, captures
the app callback, exchanges the one-time code, and either updates the GitHub
secret automatically through an already-authenticated GitHub CLI or copies the
refresh token to the macOS clipboard and opens the correct GitHub settings page.
No AH password or token is written to disk or printed.
"""

from __future__ import annotations

import gzip
import http.client
import json
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOGIN_HOST = "login.ah.nl"
API_BASE = "https://api.ah.nl"
TOKEN_URL = f"{API_BASE}/mobile-auth/v1/auth/token"
CLIENT_ID = "appie-ios"
CLIENT_VERSION = "9.45"
USER_AGENT = "Appie/9.45 (iPhone; iPhone OS)"
APPLICATION = "AHWEBSHOP"
LOGIN_TIMEOUT_SECONDS = 600
REPO = "EVGHacc/ah-last-chance-scanner"
SECRET_NAME = "AH_REFRESH_TOKEN"
GITHUB_SETTINGS_URL = f"https://github.com/{REPO}/settings/secrets/actions"
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


def sanitize_cookie(cookie: str) -> str:
    parts = cookie.split(";")
    out = [parts[0]]
    for part in parts[1:]:
        attr = part.strip()
        lower = attr.lower()
        if lower == "secure" or lower.startswith("samesite") or lower.startswith("domain"):
            continue
        out.append(part)
    return ";".join(out)


def rewrite_location(location: str, local_origin: str) -> str:
    if location.startswith("appie://"):
        parsed = urllib.parse.urlparse(location)
        query = urllib.parse.urlencode(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        return f"{local_origin}/callback" + (f"?{query}" if query else "")
    return location.replace(f"https://{LOGIN_HOST}", local_origin)


def rewrite_body(body: bytes, local_origin: str) -> bytes:
    for old, new in (
        (b"appie://login-exit", f"{local_origin}/callback".encode()),
        (f"https://{LOGIN_HOST}".encode(), local_origin.encode()),
    ):
        body = body.replace(old, new)
    return body


def exchange_code(code: str) -> dict:
    payload = json.dumps({"clientId": CLIENT_ID, "code": code}).encode()
    headers = {
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": USER_AGENT, "x-client-name": CLIENT_ID,
        "x-client-version": CLIENT_VERSION, "x-application": APPLICATION,
    }
    req = urllib.request.Request(TOKEN_URL, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"AH token exchange mislukt: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AH token exchange mislukt: {exc}") from exc
    return json.loads(raw)


def copy_to_clipboard(value: str) -> bool:
    pbcopy = shutil.which("pbcopy")
    if not pbcopy:
        return False
    subprocess.run([pbcopy], input=value, text=True, check=True)
    return True


def try_update_github_secret(value: str) -> bool:
    gh = shutil.which("gh")
    if not gh:
        return False
    auth = subprocess.run([gh, "auth", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if auth.returncode != 0:
        return False
    result = subprocess.run(
        [gh, "secret", "set", SECRET_NAME, "--repo", REPO],
        input=value, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    if result.returncode == 0:
        return True
    return False


class LoginState:
    def __init__(self) -> None:
        self.code = ""
        self.event = threading.Event()
        self.error = ""


def make_handler(state: LoginState, local_origin: str):
    class ProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:
            return

        def _callback(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            code = urllib.parse.parse_qs(parsed.query).get("code", [""])[0].strip()
            if not code:
                self.send_error(400, "OAuth-code ontbreekt")
                return
            state.code = code
            state.event.set()
            page = (
                "<!doctype html><meta charset=utf-8><title>AH login gelukt</title>"
                "<body style='font-family:system-ui;max-width:520px;margin:80px auto'>"
                "<h1>AH-login gelukt</h1><p>Je kunt dit tabblad sluiten en teruggaan naar Terminal.</p>"
                "<script>setTimeout(()=>window.close(),800)</script></body>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

        def _proxy(self) -> None:
            content_length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(content_length) if content_length else None
            headers = {}
            for key, value in self.headers.items():
                lower = key.lower()
                if lower in HOP_BY_HOP or lower in {"host", "content-length", "accept-encoding"}:
                    continue
                if lower == "origin" and value.startswith(local_origin):
                    value = f"https://{LOGIN_HOST}"
                elif lower == "referer":
                    value = value.replace(local_origin, f"https://{LOGIN_HOST}")
                headers[key] = value
            headers["Host"] = LOGIN_HOST
            headers["Accept-Encoding"] = "identity"

            conn = http.client.HTTPSConnection(LOGIN_HOST, timeout=30)
            try:
                conn.request(self.command, self.path, body=body, headers=headers)
                resp = conn.getresponse()
                status, reason = resp.status, resp.reason
                data = resp.read()
                response_headers = resp.getheaders()
            except Exception as exc:
                state.error = f"Loginproxy fout: {exc}"
                state.event.set()
                self.send_error(502, "AH-loginproxy kon upstream niet bereiken")
                return
            finally:
                conn.close()

            header_map = {k.lower(): v for k, v in response_headers}
            content_encoding = header_map.get("content-encoding", "").lower()
            if content_encoding == "gzip":
                try:
                    data = gzip.decompress(data)
                    content_encoding = ""
                except OSError:
                    pass
            content_type = header_map.get("content-type", "").lower()
            if any(kind in content_type for kind in ("text/html", "javascript", "json")):
                data = rewrite_body(data, local_origin)

            self.send_response(status, reason)
            for key, value in response_headers:
                lower = key.lower()
                if lower in HOP_BY_HOP or lower in {
                    "content-length", "content-encoding", "content-security-policy",
                    "strict-transport-security", "x-frame-options", "set-cookie", "location",
                }:
                    continue
                self.send_header(key, value)
            for key, value in response_headers:
                if key.lower() == "set-cookie":
                    self.send_header("Set-Cookie", sanitize_cookie(value))
            location = next((v for k, v in response_headers if k.lower() == "location"), "")
            if location:
                self.send_header("Location", rewrite_location(location, local_origin))
            if content_encoding:
                self.send_header("Content-Encoding", content_encoding)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_GET(self) -> None:
            if urllib.parse.urlparse(self.path).path == "/callback":
                self._callback()
            else:
                self._proxy()
        def do_POST(self) -> None: self._proxy()
        def do_PUT(self) -> None: self._proxy()
        def do_PATCH(self) -> None: self._proxy()
        def do_DELETE(self) -> None: self._proxy()
        def do_OPTIONS(self) -> None: self._proxy()

    return ProxyHandler


def run_login() -> str:
    state = LoginState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    host, port = server.server_address
    local_origin = f"http://{host}:{port}"
    server.RequestHandlerClass = make_handler(state, local_origin)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    query = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code", "redirect_uri": "appie://login-exit",
    })
    print("AH-login wordt geopend. Log normaal in in je browser.")
    webbrowser.open(f"{local_origin}/login?{query}")
    try:
        if not state.event.wait(LOGIN_TIMEOUT_SECONDS):
            raise RuntimeError("Timeout: binnen 10 minuten geen AH-login afgerond.")
        if state.error:
            raise RuntimeError(state.error)
        if not state.code:
            raise RuntimeError("AH-login afgerond zonder OAuth-code.")
        return state.code
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def main() -> int:
    print("AH scanner herstellen")
    print("=====================")
    print("Je hoeft geen map, repo of bestand op je Mac te zoeken.\n")
    try:
        token = exchange_code(run_login())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    refresh = str(token.get("refresh_token") or "").strip()
    if not refresh:
        print("AH gaf geen refresh token terug.", file=sys.stderr)
        return 1

    if try_update_github_secret(refresh):
        print("\nKlaar: GitHub secret AH_REFRESH_TOKEN is automatisch bijgewerkt via GitHub CLI.")
        print("Stuur in ChatGPT alleen: secret bijgewerkt")
        return 0

    if not copy_to_clipboard(refresh):
        print("Kon de token niet veilig naar het macOS-klembord kopiëren.", file=sys.stderr)
        return 1

    print("\nDe nieuwe token staat op je klembord.")
    print("Ik open nu direct de juiste GitHub-instellingen.")
    print("Klik AH_REFRESH_TOKEN -> Update, druk Cmd+V en sla op.")
    print("Daarna hoef je alleen in ChatGPT te zeggen: secret bijgewerkt")
    webbrowser.open(GITHUB_SETTINGS_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
