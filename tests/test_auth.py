"""Tests for auth token handling."""

import base64
import json
import time

from sugarlearning_tools.auth import _decode_jwt_expiry, _decode_jwt_payload, _extract_user_id, _is_expired


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


# --- _decode_jwt_payload ---

def test_decode_jwt_payload():
    token = _make_jwt({"sub": "user1", "email": "jk@ssw.com.au"})
    payload = _decode_jwt_payload(token)
    assert payload is not None
    assert payload["sub"] == "user1"
    assert payload["email"] == "jk@ssw.com.au"


def test_decode_jwt_payload_invalid():
    assert _decode_jwt_payload("not-a-jwt") is None
    assert _decode_jwt_payload("") is None


# --- _extract_user_id ---

def test_extract_user_id_from_email():
    token = _make_jwt({"email": "jk@ssw.com.au"})
    assert _extract_user_id(token) == "jk"


def test_extract_user_id_long_email():
    token = _make_jwt({"email": "john.smith@example.com"})
    assert _extract_user_id(token) == "john.smith"


def test_extract_user_id_no_email():
    token = _make_jwt({"sub": "user1"})
    assert _extract_user_id(token) is None


def test_extract_user_id_invalid_token():
    assert _extract_user_id("not-a-jwt") is None
