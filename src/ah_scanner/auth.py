"""AH authenticatie: refresh-token, rotatie en versleutelde state.

De envelope (AES-256-GCM, sleutel afgeleid van AH_REFRESH_TOKEN) is compatibel met
het bestaande ``data/auth_state.enc``. Er worden nooit tokens of response-bodies gelogd.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://api.ah.nl"
REFRESH_PATH = "/mobile-auth/v1/auth/token/refresh"
CLIENT_ID = "appie-ios"
HEADERS = {
    "User-Agent": "Appie/9.28 (iPhone17,3; iPhone; CPU OS 26_1 like Mac OS X)",
    "x-client-name": CLIENT_ID,
    "x-client-version": "9.28",
    "x-application": "AHWEBSHOP",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
_AAD = b"ah-last-chance-auth-state-v1"

PostFn = Callable[[str, dict], tuple[int, dict]]


class AuthError(RuntimeError):
    """Authenticatiefout met een stabiele, niet-geheime code."""

    def __init__(self, code: str, status: int):
        self.code = code
        self.status = status
        super().__init__(f"{code} (HTTP {status})")


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    rotated: bool


def _key(root_secret: str) -> bytes:
    if not root_secret:
        raise ValueError("root secret ontbreekt")
    return hashlib.sha256(b"ah-last-chance-root-key-v1\x00" + root_secret.encode()).digest()


def _aesgcm():
    """AESGCM pas bij gebruik importeren: report en export hebben cryptography niet nodig.

    Een kapotte installatie geeft hier een duidelijke ImportError in plaats van een crash bij het
    opstarten van elk commando.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM


def require_cryptography() -> None:
    """Faal vroeg als versleutelen niet kan, vóór een refresh het token laat roteren.

    Zonder dit zou een scan eerst verversen (AH roteert dan de refresh-token) en daarna crashen
    bij het opslaan, waardoor de geroteerde token verloren gaat.
    """
    _aesgcm()


def seal(refresh_token: str, root_secret: str) -> str:
    payload = json.dumps(
        {"refreshToken": refresh_token, "issuedAtNs": time.time_ns()}, separators=(",", ":")
    ).encode()
    nonce = os.urandom(12)
    ciphertext = _aesgcm()(_key(root_secret)).encrypt(nonce, payload, _AAD)
    return (
        json.dumps(
            {
                "version": 1,
                "algorithm": "AES-256-GCM",
                "nonce": base64.urlsafe_b64encode(nonce).decode(),
                "ciphertext": base64.urlsafe_b64encode(ciphertext).decode(),
            },
            separators=(",", ":"),
        )
        + "\n"
    )


def unseal(path: Path, root_secret: str) -> str:
    """Geef de opgeslagen refresh-token, of '' als die ontbreekt of niet te lezen is.

    Een kapotte cryptography-installatie is geen "niet te lezen": die geeft een ImportError, zodat
    het niet als "opnieuw inloggen" wordt gemeld.
    """
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        if int(envelope.get("version", 0)) != 1:
            return ""
        nonce = base64.urlsafe_b64decode(envelope["nonce"])
        ciphertext = base64.urlsafe_b64decode(envelope["ciphertext"])
    except Exception:
        return ""
    aesgcm = _aesgcm()
    try:
        plain = aesgcm(_key(root_secret)).decrypt(nonce, ciphertext, _AAD)
        return str(json.loads(plain).get("refreshToken") or "").strip()
    except Exception:
        return ""


def http_post(path: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE_URL + path, data=json.dumps(body).encode(), headers=HEADERS, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {}
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, {}


def _try_refresh(token: str, post: PostFn) -> tuple[int, dict]:
    return post(REFRESH_PATH, {"clientId": CLIENT_ID, "refreshToken": token})


def refresh_session(
    secret: str,
    sealed_path: Path | None,
    post: PostFn = http_post,
    sleep: Callable[[float], None] = time.sleep,
    transient_delays: tuple[float, ...] = (0, 2, 5),
) -> Session:
    """Ververs de sessie. Probeert eerst de versleutelde (nieuwste) token, dan de secret.

    Begrensd: per kandidaat maximaal ``len(transient_delays)`` pogingen, alleen bij tijdelijke
    fouten. Een afwijzing (400/401) valt één keer terug op de volgende kandidaat.
    """
    secret = (secret or "").strip()
    if not secret:
        raise AuthError("AUTH_REAUTH_REQUIRED", 0)
    candidates: list[str] = []
    sealed = unseal(sealed_path, secret) if sealed_path else ""
    for token in (sealed, secret):
        if token and token not in candidates:
            candidates.append(token)

    last_status = 0
    for token in candidates:
        for delay in transient_delays:
            if delay:
                sleep(delay)
            status, payload = _try_refresh(token, post)
            last_status = status
            access = str(payload.get("access_token") or "").strip()
            if status == 200 and access:
                new_refresh = str(payload.get("refresh_token") or "").strip() or token
                return Session(access, new_refresh, new_refresh != token)
            if status in (400, 401):
                break  # afgewezen: volgende kandidaat
            if status not in (0, 408, 425, 429, 500, 502, 503, 504):
                raise AuthError("AUTH_REFRESH_FAILED", status)
        else:
            raise AuthError("AUTH_REFRESH_RETRY_EXHAUSTED", last_status)
    raise AuthError("AUTH_REAUTH_REQUIRED", last_status)


def persist_rotation(session: Session, secret: str, sealed_path: Path) -> bool:
    """Sla een geroteerde refresh-token versleuteld op. Geeft True als er is geschreven."""
    if not session.rotated:
        return False
    sealed_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = sealed_path.with_suffix(sealed_path.suffix + ".tmp")
    tmp.write_text(seal(session.refresh_token, secret), encoding="utf-8")
    tmp.replace(sealed_path)
    return True
