import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.infrastructure.models import OutboxEventRow
from shared.infrastructure.outbox_processor import OutboxProcessor
from shared.infrastructure.unit_of_work import SqlAlchemyAuditLogger


@pytest.mark.asyncio
async def test_outbox_processor_marks_pending(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        session.add(
            OutboxEventRow(
                id=uuid.uuid4(),
                type="test.event",
                payload_json={"hello": "world"},
                status="pending",
            )
        )
        await session.commit()

    async with session_factory() as session:
        processor = OutboxProcessor(session)
        count = await processor.process_pending()
        assert count == 1

    async with session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(select(OutboxEventRow))
        row = result.scalars().first()
        assert row is not None
        assert row.status == "processed"
        assert row.processed_at is not None


@pytest.mark.asyncio
async def test_audit_logger_writes_identity_audit(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        logger = SqlAlchemyAuditLogger(session)
        await logger.log("test.audit", actor_user_id=uuid.uuid4())
        await session.commit()

    async with session_factory() as session:
        from sqlalchemy import select
        from identity.infrastructure.models import AuditLogRow

        result = await session.execute(select(AuditLogRow))
        row = result.scalars().first()
        assert row is not None
        assert row.event_action == "test.audit"
