from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from identity.infrastructure.models import DeliverySecretRow
from shared.infrastructure.models import OutboxEventRow

logger = logging.getLogger(__name__)


class NotificationSink:
    """In-memory / log sink for delivered messages (dev, test, stub production)."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def record(self, channel: str, *, to: str, body: dict[str, Any]) -> None:
        entry = {"channel": channel, "to": to, **body}
        self.messages.append(entry)
        logger.info("notification.%s to=%s keys=%s", channel, to, sorted(body.keys()))


class OutboxProcessor:
    """
    Processes pending outbox events (H3).
    Never leaves plaintext secrets in outbox payloads after success (C1).
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        sink: NotificationSink | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session = session
        self._sink = sink or NotificationSink()
        self._session_factory = session_factory

    async def process_pending(self, limit: int = 100) -> int:
        result = await self._session.execute(
            select(OutboxEventRow)
            .where(OutboxEventRow.status == "pending")
            .order_by(OutboxEventRow.created_at)
            .limit(limit)
        )
        rows = list(result.scalars().all())
        processed = 0
        for row in rows:
            try:
                await self._handle(row)
                row.status = "processed"
                row.processed_at = datetime.now(timezone.utc)
                # Redact any residual secret-shaped keys from payload
                payload = dict(row.payload_json or {})
                for key in ("otp_code", "reset_token", "secret", "password"):
                    payload.pop(key, None)
                payload["secret_redacted"] = True
                row.payload_json = payload
                processed += 1
            except Exception:
                row.retry_count = (row.retry_count or 0) + 1
                if row.retry_count >= 5:
                    row.status = "dead"
                logger.exception("outbox handle failed id=%s type=%s", row.id, row.type)
        await self._session.commit()
        return processed

    async def _handle(self, row: OutboxEventRow) -> None:
        payload = row.payload_json or {}
        if row.type == "send_verification_email":
            await self._deliver_secret(
                purpose="verification_email",
                delivery_secret_id=payload.get("delivery_secret_id"),
                email=payload.get("email", ""),
                channel="verification_email",
                extra={"user_id": payload.get("user_id"), "verification_token_id": payload.get("verification_token_id")},
            )
        elif row.type == "send_password_reset_email":
            await self._deliver_secret(
                purpose="password_reset_email",
                delivery_secret_id=payload.get("delivery_secret_id"),
                email=payload.get("email", ""),
                channel="password_reset_email",
                extra={"reset_token_id": payload.get("reset_token_id")},
            )
        elif row.type == "retry_keycloak_set_password":
            # Compensating / retry hook — logged for operator; real KC adapter wires later.
            logger.warning("outbox retry_keycloak_set_password payload=%s", payload)
            self._sink.record("keycloak_set_password_retry", to="keycloak", body=payload)
        else:
            logger.info("outbox unknown type=%s id=%s — marking processed", row.type, row.id)

    async def _deliver_secret(
        self,
        *,
        purpose: str,
        delivery_secret_id: str | None,
        email: str,
        channel: str,
        extra: dict[str, Any],
    ) -> None:
        if not delivery_secret_id:
            raise ValueError("delivery_secret_id required")
        secret_row = await self._session.get(DeliverySecretRow, UUID(str(delivery_secret_id)))
        if secret_row is None or secret_row.purpose != purpose:
            raise ValueError("delivery secret not found")
        if secret_row.consumed_at is not None:
            return
        if secret_row.expires_at < datetime.now(timezone.utc):
            secret_row.secret_plain = None
            secret_row.consumed_at = datetime.now(timezone.utc)
            raise ValueError("delivery secret expired")

        plaintext = secret_row.secret_plain
        if not plaintext:
            raise ValueError("delivery secret already wiped")

        self._sink.record(channel, to=email, body={"secret": plaintext, **extra})
        secret_row.secret_plain = None
        secret_row.consumed_at = datetime.now(timezone.utc)
        await self._session.flush()
