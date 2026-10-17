"""Ensure platform team membership rows exist for operators."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain.security import utcnow
from platform_ops.infrastructure.models import PlatformTeamMemberRow


async def upsert_operator_team_member(
    session: AsyncSession,
    *,
    email: str,
    user_id: UUID | None = None,
    platform_role: str = "platform_admin",
    invited_by: UUID | None = None,
    status: str | None = None,
) -> PlatformTeamMemberRow:
    normalized = email.strip().lower()
    existing = (
        await session.execute(
            select(PlatformTeamMemberRow).where(PlatformTeamMemberRow.email == normalized)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if user_id is not None and existing.user_id is None:
            existing.user_id = user_id
        if existing.status == "invited" and user_id is not None:
            existing.status = "active"
            existing.activated_at = utcnow()
        return existing

    resolved_status = status or ("active" if user_id is not None else "invited")
    row = PlatformTeamMemberRow(
        id=uuid.uuid4(),
        user_id=user_id,
        email=normalized,
        platform_role=platform_role,
        status=resolved_status,
        invited_by=invited_by,
        activated_at=utcnow() if resolved_status == "active" else None,
    )
    session.add(row)
    await session.flush()
    return row
