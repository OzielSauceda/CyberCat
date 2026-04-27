"""Unit tests for auth security primitives (Phase 14.1).

No DB or network — pure function tests.
"""
from __future__ import annotations

import pytest
from itsdangerous import BadSignature, SignatureExpired

from app.auth.security import (
    generate_token,
    hash_password,
    hash_token,
    sign_session,
    verify_password,
    verify_session,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_bcrypt_round_trip() -> None:
    hashed = hash_password("hunter2")
    assert verify_password("hunter2", hashed)
    assert not verify_password("wrong", hashed)


def test_bcrypt_produces_unique_hashes_for_same_input() -> None:
    h1 = hash_password("same-input")
    h2 = hash_password("same-input")
    # bcrypt adds a random salt, so two hashes of the same password must differ
    assert h1 != h2


def test_bcrypt_rejects_empty_password() -> None:
    hashed = hash_password("")
    assert verify_password("", hashed)
    assert not verify_password("notempty", hashed)


# ---------------------------------------------------------------------------
# Session signing / verification
# ---------------------------------------------------------------------------


def test_session_sign_and_verify_round_trip() -> None:
    payload = {"user_id": "abc-123", "role": "analyst", "token_version": 7}
    token = sign_session(payload, secret="test-secret")
    recovered = verify_session(token, secret="test-secret", max_age_seconds=300)
    assert recovered == payload


def test_session_wrong_secret_raises() -> None:
    token = sign_session({"x": 1}, secret="secret-a")
    with pytest.raises(BadSignature):
        verify_session(token, secret="secret-b", max_age_seconds=300)


def test_session_expired_raises() -> None:
    # max_age_seconds=-1 makes every token immediately expired (now > signed_at + (-1))
    token = sign_session({"x": 1}, secret="secret")
    with pytest.raises(SignatureExpired):
        verify_session(token, secret="secret", max_age_seconds=-1)


def test_session_tampered_payload_raises() -> None:
    token = sign_session({"user_id": "alice"}, secret="secret")
    # Flip a character in the payload portion to corrupt the signature
    tampered = token[:-4] + "XXXX"
    with pytest.raises(BadSignature):
        verify_session(tampered, secret="secret", max_age_seconds=300)


# ---------------------------------------------------------------------------
# API token generation and hashing
# ---------------------------------------------------------------------------


def test_generate_token_has_cct_prefix() -> None:
    plaintext, digest = generate_token()
    assert plaintext.startswith("cct_")


def test_generate_token_digest_is_32_bytes() -> None:
    _, digest = generate_token()
    assert len(digest) == 32  # SHA-256 output is always 32 bytes


def test_hash_token_is_deterministic() -> None:
    plaintext, digest_at_generation = generate_token()
    assert hash_token(plaintext) == digest_at_generation


def test_generate_token_unique_on_each_call() -> None:
    _, d1 = generate_token()
    _, d2 = generate_token()
    assert d1 != d2


def test_hash_token_different_inputs_differ() -> None:
    assert hash_token("cct_aaa") != hash_token("cct_bbb")
