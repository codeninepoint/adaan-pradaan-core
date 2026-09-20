from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from shared.application.ports import UnitOfWork


class SessionUnitOfWork(UnitOfWork):
    """Transaction boundary bound to the request-scoped SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def __aenter__(self) -> SessionUnitOfWork:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type:
            await self.session.rollback()
