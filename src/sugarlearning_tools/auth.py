"""Auth for SugarLearning API.

Two modes:
1. 'sl login' — paste a Bearer token from browser DevTools (simple, works immediately)
2. 'sl login --oauth' — full OAuth PKCE flow via browser (requires redirect URI to be registered)

The pasted token is stored locally. When it expires (1 hour), you can either:
- Paste a new one with 'sl login'
- If you have a refresh token (from OAuth flow), it auto-refreshes
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Event
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

from .config import get_settings

_SCOPES = "openid profile email offline_access ssw-sugarlearning-api"


def _load_tokens() -> dict | None:
    settings = get_settings()
    if settings.token_path.exists():
        return json.loads(settings.token_path.read_text())
    return None


def _save_tokens(tokens: dict) -> None:
    settings = get_settings()
    settings.token_path.write_text(json.dumps(tokens, indent=2))


def _is_expired(tokens: dict) -> bool:
    return time.time() >= tokens.get("expires_at", 0) - 60  # 60s buffer


def _discover_endpoints(authority: str) -> dict:
    """Fetch OpenID Connect discovery document."""
    resp = httpx.get(f"{authority}/.well-known/openid-configuration", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _refresh_tokens(refresh_token: str, discovery: dict) -> dict:
    """Use refresh token to get new access token."""
    settings = get_settings()
    resp = httpx.post(
        discovery["token_endpoint"],
        data={
            "grant_type": "refresh_token",
            "client_id": settings.client_id,
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    data["expires_at"] = time.time() + data.get("expires_in", 3600)
    return data


def _decode_jwt_expiry(token: str) -> float | None:
    """Extract expiry time from a JWT without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Decode payload (add padding)
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("exp")
    except Exception:
        return None


def login_with_refresh_token(refresh_token: str) -> dict:
    """Store a refresh token and immediately get a fresh access token."""
    settings = get_settings()
    discovery = _discover_endpoints(settings.identity_authority)
    tokens = _refresh_tokens(refresh_token.strip(), discovery)
    if "refresh_token" not in tokens:
        tokens["refresh_token"] = refresh_token.strip()
    _save_tokens(tokens)
    remaining = int(tokens["expires_at"] - time.time())
    print(f"Login successful via refresh token! Access token valid for {remaining // 60} minutes.")
    print("Token will auto-refresh when it expires.")
    return tokens


def login_with_token(bearer_token: str) -> dict:
    """Store a manually-provided Bearer token.

    Extracts expiry from the JWT payload so we know when it expires.
    """
    token = bearer_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    exp = _decode_jwt_expiry(token)
    tokens = {
        "access_token": token,
        "expires_at": exp or (time.time() + 3600),  # default 1h if can't decode
    }

    # Preserve existing refresh token if we have one
    existing = _load_tokens()
    if existing and "refresh_token" in existing:
        tokens["refresh_token"] = existing["refresh_token"]

    _save_tokens(tokens)
    if exp:
        remaining = int(exp - time.time())
        mins = remaining // 60
        print(f"Token saved. Expires in ~{mins} minutes.")
    else:
        print("Token saved (could not determine expiry).")
    return tokens


def login_oauth() -> dict:
    """Interactive OAuth PKCE login via browser.

    NOTE: This requires the redirect URI to be registered with the Identity Server.
    The default SugarLearning client uses specific redirect URIs. If this fails
    with 'invalid_request', use 'sl login' to paste a token instead.
    """
    settings = get_settings()
    discovery = _discover_endpoints(settings.identity_authority)

    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    state = secrets.token_urlsafe(32)
    auth_code: dict[str, str | None] = {"code": None, "error": None}
    done = Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = parse_qs(urlparse(self.path).query)
            if qs.get("state", [None])[0] != state:
                auth_code["error"] = "State mismatch"
            elif "error" in qs:
                auth_code["error"] = qs["error"][0]
            else:
                auth_code["code"] = qs.get("code", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if auth_code["code"]:
                self.wfile.write(b"<h1>Login successful!</h1><p>You can close this tab.</p>")
            else:
                self.wfile.write(f"<h1>Login failed: {auth_code['error']}</h1>".encode())
            done.set()

        def log_message(self, format, *args):
            pass

    authorize_url = discovery["authorization_endpoint"] + "?" + urlencode({
        "client_id": settings.client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })

    server = HTTPServer(("localhost", 8912), CallbackHandler)
    server.timeout = 120

    print("Opening browser for login...")
    webbrowser.open(authorize_url)

    while not done.is_set():
        server.handle_request()

    server.server_close()

    if auth_code["error"]:
        raise RuntimeError(f"Login failed: {auth_code['error']}")
    if not auth_code["code"]:
        raise RuntimeError("No authorization code received")

    resp = httpx.post(
        discovery["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "client_id": settings.client_id,
            "code": auth_code["code"],
            "redirect_uri": settings.redirect_uri,
            "code_verifier": verifier,
        },
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 3600)
    _save_tokens(tokens)
    print("Login successful! Tokens saved.")
    return tokens


def get_token() -> str:
    """Get a valid access token, refreshing if needed.

    Returns the access token string ready for Bearer header.
    Raises RuntimeError if no tokens and interactive login is needed.
    """
    tokens = _load_tokens()
    if tokens is None:
        raise RuntimeError("Not logged in. Run 'sl login' first.")

    if not _is_expired(tokens):
        return tokens["access_token"]

    # Try refresh if we have a refresh token
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "Access token expired and no refresh token available.\n"
            "Run 'sl login' to paste a fresh token from browser DevTools.\n\n"
            "Tip: In Chrome DevTools > Network tab, find any API request to\n"
            "my.sugarlearning.com and copy the Authorization header value."
        )

    settings = get_settings()
    discovery = _discover_endpoints(settings.identity_authority)

    try:
        new_tokens = _refresh_tokens(refresh_token, discovery)
        if "refresh_token" not in new_tokens:
            new_tokens["refresh_token"] = refresh_token
        _save_tokens(new_tokens)
        return new_tokens["access_token"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 401):
            raise RuntimeError(
                "Refresh token expired. Run 'sl login' to paste a fresh token."
            ) from e
        raise
