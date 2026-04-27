from __future__ import annotations

import hashlib
import secrets
from typing import Any

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer  # noqa: F401 (re-exported)

_BCRYPT_ROUNDS = 12
_SESSION_SALT = "cybercat-session-v1"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def sign_session(payload: dict[str, Any], secret: str) -> str:
    s = URLSafeTimedSerializer(secret, salt=_SESSION_SALT)
    return s.dumps(payload)


def verify_session(token: str, secret: str, max_age_seconds: int) -> dict[str, Any]:
    """Raises BadSignature or SignatureExpired if the token is invalid or expired."""
    s = URLSafeTimedSerializer(secret, salt=_SESSION_SALT)
    return s.loads(token, max_age=max_age_seconds)


def generate_token() -> tuple[str, bytes]:
    """Return (plaintext_with_cct_prefix, sha256_digest_bytes).

    The caller MUST store only the digest. The plaintext is shown once and discarded.
    """
    raw = secrets.token_urlsafe(32)
    plaintext = f"cct_{raw}"
    return plaintext, _sha256(plaintext)


def hash_token(plaintext: str) -> bytes:
    """Return the sha256 digest used for storage and lookup."""
    return _sha256(plaintext)


def _sha256(text: str) -> bytes:
    return hashlib.sha256(text.encode()).digest()
