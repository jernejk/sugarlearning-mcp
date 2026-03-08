"""Tests for auth token handling."""

import base64
import json
import time

from sugarlearning_tools.auth import _decode_jwt_expiry, _is_expired


def _make_jwt(payload: dict) -> str:
    """Create a fake JWT with the given payload (no signature verification)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesignature"


def test_decode_jwt_expiry():
    exp = int(time.time()) + 3600
    token = _make_jwt({"sub": "user1", "exp": exp})
    assert _decode_jwt_expiry(token) == exp


def test_decode_jwt_expiry_no_exp():
    token = _make_jwt({"sub": "user1"})
    assert _decode_jwt_expiry(token) is None


def test_decode_jwt_expiry_invalid_token():
    assert _decode_jwt_expiry("not-a-jwt") is None
    assert _decode_jwt_expiry("") is None
    assert _decode_jwt_expiry("a.b") is None


def test_is_expired_not_expired():
    tokens = {"expires_at": time.time() + 300}
    assert not _is_expired(tokens)


def test_is_expired_past():
    tokens = {"expires_at": time.time() - 10}
    assert _is_expired(tokens)


def test_is_expired_within_buffer():
    # Within 60s buffer should be considered expired
    tokens = {"expires_at": time.time() + 30}
    assert _is_expired(tokens)


def test_is_expired_no_key():
    tokens = {}
    assert _is_expired(tokens)
