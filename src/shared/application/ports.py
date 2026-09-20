from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


class AuditLogger(Protocol):
    async def log(
        self,
        event_action: str,
        *,
        actor_user_id: UUID | None = None,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None: ...


class OutboxPublisher(Protocol):
    async def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class UnitOfWork(Protocol):
    session: AsyncSession

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def __aenter__(self) -> UnitOfWork: ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
