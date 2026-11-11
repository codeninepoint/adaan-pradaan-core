"""Cashfree webhook signature verification.

signedPayload = timestamp + rawBody
expectedSignature = Base64(HMAC-SHA256(signedPayload, secret))
"""

from __future__ import annotations

import base64
import hashlib
import hmac


def verify_cashfree_signature(
    *,
    raw_body: str | bytes,
    timestamp: str,
    signature: str,
    secret: str,
) -> bool:
    if not secret or not timestamp or not signature:
        return False
    body = raw_body.decode("utf-8") if isinstance(raw_body, (bytes, bytearray)) else raw_body
    signed = f"{timestamp}{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def sign_cashfree_payload(*, raw_body: str, timestamp: str, secret: str) -> str:
    """Helper for tests / stub webhook simulation."""
    signed = f"{timestamp}{raw_body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")
