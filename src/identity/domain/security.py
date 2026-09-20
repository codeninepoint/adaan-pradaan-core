"""Identity domain security helpers (no infrastructure imports)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext

from shared.settings import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_secret(value: str) -> str:
    return _pwd_context.hash(value)


def verify_secret(value: str, hashed: str) -> bool:
    return _pwd_context.verify(value, hashed)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def otp_expires_at() -> datetime:
    return utcnow() + timedelta(minutes=settings.otp_ttl_minutes)


def refresh_expires_at() -> datetime:
    return utcnow() + timedelta(days=settings.jwt_refresh_ttl_days)


def split_reset_token(composite: str) -> tuple[str, str] | None:
    """Parse `{token_id}.{secret}` reset token format."""
    if not composite or "." not in composite:
        return None
    token_id, _, secret = composite.partition(".")
    if not token_id or not secret:
        return None
    return token_id, secret


def make_reset_token_composite(token_id: str, secret: str) -> str:
    return f"{token_id}.{secret}"
