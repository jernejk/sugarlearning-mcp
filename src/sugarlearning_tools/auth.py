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
import os
import secrets
import sys
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Event
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

from .config import get_settings, _CONFIG_HOME, reset_settings

_SCOPES = "openid profile email offline_access ssw-sugarlearning-api"


def _load_tokens() -> dict | None:
    settings = get_settings()
    if settings.token_path.exists():
        return json.loads(settings.token_path.read_text())
    return None


def _save_tokens(tokens: dict) -> None:
    settings = get_settings()
    path = settings.token_path
    path.write_text(json.dumps(tokens, indent=2))
    os.chmod(path, 0o600)


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


def _decode_jwt_payload(token: str) -> dict | None:
    """Decode a JWT payload without verifying signature."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Decode payload (add padding)
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return None


def _decode_jwt_expiry(token: str) -> float | None:
    """Extract expiry time from a JWT without verifying signature."""
    payload = _decode_jwt_payload(token)
    return payload.get("exp") if payload else None


def _extract_user_id(token: str) -> str | None:
    """Extract user ID from JWT email claim (email prefix before @)."""
    payload = _decode_jwt_payload(token)
    if not payload:
        return None
    email = payload.get("email", "")
    if "@" in email:
        return email.split("@")[0]
    return None


def _maybe_save_user_id(token: str) -> None:
    """Auto-save user_id to .env if not already configured."""
    settings = get_settings()
    if settings.user_id:
        return  # Already configured
    user_id = _extract_user_id(token)
    if not user_id:
        return
    # Update .env in config home
    env_path = _CONFIG_HOME / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing = env_path.read_text() if env_path.exists() else ""
    if "SL_USER_ID" not in existing:
        with env_path.open("a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"SL_USER_ID={user_id}\n")
        reset_settings()
        print(f"Auto-detected user ID: {user_id}", file=sys.stderr)


def login_with_refresh_token(refresh_token: str) -> dict:
    """Store a refresh token and immediately get a fresh access token."""
    settings = get_settings()
    discovery = _discover_endpoints(settings.identity_authority)
    tokens = _refresh_tokens(refresh_token.strip(), discovery)
    if "refresh_token" not in tokens:
        tokens["refresh_token"] = refresh_token.strip()
    _save_tokens(tokens)
    _maybe_save_user_id(tokens["access_token"])
    remaining = int(tokens["expires_at"] - time.time())
    print(f"Login successful via refresh token! Access token valid for {remaining // 60} minutes.", file=sys.stderr)
    print("Token will auto-refresh when it expires.", file=sys.stderr)
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
    _maybe_save_user_id(token)
    if exp:
        remaining = int(exp - time.time())
        mins = remaining // 60
        print(f"Token saved. Expires in ~{mins} minutes.", file=sys.stderr)
    else:
        print("Token saved (could not determine expiry).", file=sys.stderr)
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

    # Parse port from redirect_uri setting
    redirect_parsed = urlparse(settings.redirect_uri)
    port = redirect_parsed.port or 8912
    server = HTTPServer(("localhost", port), CallbackHandler)
    server.timeout = 120

    print("Opening browser for login...", file=sys.stderr)
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
    _maybe_save_user_id(tokens["access_token"])
    print("Login successful! Tokens saved.", file=sys.stderr)
    return tokens


def login_with_browser(timeout_sec: int = 300) -> dict:
    """Open a real browser via Playwright, let the user log in normally,
    then sniff the Authorization header from the first API request.

    This sidesteps OAuth PKCE entirely — we don't need a registered CLI
    redirect URI because we ride on the web app's own login flow.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright is not installed. Run:\n"
            "  uv pip install -e '.[browser]'\n"
            "  playwright install chromium"
        ) from e

    settings = get_settings()
    captured: dict[str, str | None] = {"token": None}
    api_host = urlparse(settings.base_url).netloc

    def on_request(request):
        if captured["token"]:
            return
        if api_host not in request.url:
            return
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            # Sanity-check it looks like a JWT
            if token.count(".") == 2:
                captured["token"] = token

    print("Opening browser — log in to SugarLearning normally.", file=sys.stderr)
    print("This window will close automatically once a token is captured.", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.on("request", on_request)
        page.goto(settings.base_url)

        deadline = time.time() + timeout_sec
        while not captured["token"] and time.time() < deadline:
            try:
                page.wait_for_timeout(500)
            except Exception:
                break  # page/browser closed
        try:
            browser.close()
        except Exception:
            pass

    if not captured["token"]:
        raise RuntimeError("Timed out waiting for login (no Bearer token seen).")

    print("Token captured from browser.", file=sys.stderr)
    return login_with_token(captured["token"])


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
