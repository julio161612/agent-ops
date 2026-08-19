import enum
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(enum.StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    *, subject: uuid.UUID, tenant_id: uuid.UUID, token_type: TokenType, expires_delta: timedelta
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "tenant_id": str(tenant_id),
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return _create_token(
        subject=user_id,
        tenant_id=tenant_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return _create_token(
        subject=user_id,
        tenant_id=tenant_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises jwt.PyJWTError on failure/expiry."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def generate_api_key(prefix: str) -> str:
    """A fresh random API key: ``<prefix><43 url-safe chars>`` (32 bytes of entropy)."""
    return f"{prefix}{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    """Deterministic SHA-256 hex digest, deliberately not bcrypt.

    Unlike a password, the raw key already has 256 bits of real entropy, so a
    fast hash carries no brute-force risk — and a deterministic one is what
    makes an indexed ``WHERE key_hash = ?`` lookup possible at all. Bcrypt's
    random-per-hash salt would rule that out (you can't look up a bcrypt hash
    by input value without already knowing which row to compare against).
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
