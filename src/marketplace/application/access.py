from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.infrastructure.models import AuditLogRow
from shared.domain.exceptions import ForbiddenError, NotFoundError
from tenant.infrastructure.models import OrgMembershipRow, OrganizationRow
from vendor.infrastructure.models import VendorProfileRow


async def audit(
    session: AsyncSession,
    *,
    action: str,
    actor_user_id: UUID | None,
    payload: dict,
    tenant_id: UUID | None = None,
) -> None:
    session.add(
        AuditLogRow(
            id=uuid.uuid4(),
            event_action=action,
            actor_user_id=actor_user_id,
            tenant_id=tenant_id,
            payload_json=payload,
        )
    )


async def require_vendor_owner(
    session: AsyncSession, vendor_id: UUID, user_id: UUID
) -> VendorProfileRow:
    vendor = await session.get(VendorProfileRow, vendor_id)
    if vendor is None:
        raise NotFoundError("vendor not found")
    membership = (
        await session.execute(
            select(OrgMembershipRow.id).where(
                OrgMembershipRow.organization_id == vendor.organization_id,
                OrgMembershipRow.user_id == user_id,
                OrgMembershipRow.role == "owner",
                OrgMembershipRow.status == "active",
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise ForbiddenError("vendor admin required")
    return vendor


async def require_platform_operator(session: AsyncSession, user_id: UUID) -> None:
    row = (
        await session.execute(
            select(OrganizationRow.id)
            .join(OrgMembershipRow, OrgMembershipRow.organization_id == OrganizationRow.id)
            .where(
                OrgMembershipRow.user_id == user_id,
                OrgMembershipRow.status == "active",
                OrganizationRow.is_platform_operator.is_(True),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ForbiddenError("platform operator required")
