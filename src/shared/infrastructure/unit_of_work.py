from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.application.ports import AuditLogger, OutboxPublisher, UnitOfWork
from shared.infrastructure.models import OutboxEventRow
from shared.settings import settings


class SqlAlchemyAuditLogger(AuditLogger):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        event_action: str,
        *,
        actor_user_id: UUID | None = None,
        tenant_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        from identity.infrastructure.models import AuditLogRow

        row = AuditLogRow(
            id=uuid4(),
            event_action=event_action,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            payload_json=payload or {},
        )
        self._session.add(row)


class SqlAlchemyOutboxPublisher(OutboxPublisher):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        row = OutboxEventRow(id=uuid4(), type=event_type, payload_json=payload, status="pending")
        self._session.add(row)


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        self.session = self._session_factory()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type:
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


def create_engine_and_session_factory(database_url: str | None = None):
    url = database_url or settings.database_url
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory
