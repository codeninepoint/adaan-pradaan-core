from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from authz.domain.models import PermissionRecord
from authz.infrastructure.models import (
    AuthorizationAuditLogRow,
    PermissionRow,
    PrincipalRoleRow,
    RolePermissionRow,
    RoleRow,
)
from identity.infrastructure.models import PrincipalRow, ServiceAccountRow, UserRow
from tenant.infrastructure.models import OrgMembershipRow, OrganizationRow, TenantMembershipRow, TenantRow


class SqlAlchemyPrincipalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_status(self, principal_id: UUID) -> str | None:
        row = await self._session.get(PrincipalRow, principal_id)
        return row.status if row else None


class SqlAlchemyTenantAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_tenant_active(self, tenant_id: UUID) -> bool:
        tenant = await self._session.get(TenantRow, tenant_id)
        return tenant is not None and tenant.status == "active"

    async def has_active_tenant_membership(self, principal_id: UUID, tenant_id: UUID) -> bool:
        principal = await self._session.get(PrincipalRow, principal_id)
        if principal is None:
            return False

        if principal.principal_type == "service_account":
            result = await self._session.execute(
                select(ServiceAccountRow.id).where(
                    ServiceAccountRow.principal_id == principal_id,
                    ServiceAccountRow.tenant_id == tenant_id,
                    ServiceAccountRow.status == "active",
                )
            )
            return result.scalar_one_or_none() is not None

        user = await self._session.execute(
            select(UserRow).where(UserRow.principal_id == principal_id)
        )
        user_row = user.scalar_one_or_none()
        if user_row is None:
            return False

        result = await self._session.execute(
            select(TenantMembershipRow.id).where(
                TenantMembershipRow.tenant_id == tenant_id,
                TenantMembershipRow.user_id == user_row.id,
                TenantMembershipRow.status == "active",
            )
        )
        return result.scalar_one_or_none() is not None


class SqlAlchemyOperatorAccessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_active_operator_org_id(self, principal_id: UUID) -> UUID | None:
        user = await self._session.execute(
            select(UserRow).where(UserRow.principal_id == principal_id)
        )
        user_row = user.scalar_one_or_none()
        if user_row is None:
            return None

        result = await self._session.execute(
            select(OrganizationRow.id)
            .join(OrgMembershipRow, OrgMembershipRow.organization_id == OrganizationRow.id)
            .where(
                OrgMembershipRow.user_id == user_row.id,
                OrgMembershipRow.status == "active",
                OrganizationRow.is_platform_operator.is_(True),
                OrganizationRow.status == "active",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


class SqlAlchemyPermissionCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_code(self, code: str) -> PermissionRecord | None:
        result = await self._session.execute(select(PermissionRow).where(PermissionRow.code == code))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return PermissionRecord(
            id=row.id,
            code=row.code,
            scope_type=row.scope_type,
            status=row.status,
        )


class SqlAlchemyRoleGrantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_exact_permission_grant(
        self,
        *,
        principal_id: UUID,
        permission_id: UUID,
        scope_type: str,
        tenant_id: UUID | None,
        operator_org_id: UUID | None,
        at: datetime,
    ) -> bool:
        scope_match = (
            and_(
                PrincipalRoleRow.tenant_id == tenant_id,
                RoleRow.tenant_id == tenant_id,
                PrincipalRoleRow.operator_org_id.is_(None),
                RoleRow.operator_org_id.is_(None),
            )
            if scope_type == "tenant"
            else and_(
                PrincipalRoleRow.operator_org_id == operator_org_id,
                RoleRow.operator_org_id == operator_org_id,
                PrincipalRoleRow.tenant_id.is_(None),
                RoleRow.tenant_id.is_(None),
            )
        )

        stmt = (
            select(PrincipalRoleRow.id)
            .join(RoleRow, RoleRow.id == PrincipalRoleRow.role_id)
            .join(RolePermissionRow, RolePermissionRow.role_id == RoleRow.id)
            .join(PermissionRow, PermissionRow.id == RolePermissionRow.permission_id)
            .where(
                PrincipalRoleRow.principal_id == principal_id,
                PrincipalRoleRow.status == "active",
                PrincipalRoleRow.revoked_at.is_(None),
                PrincipalRoleRow.valid_from <= at,
                or_(PrincipalRoleRow.valid_until.is_(None), PrincipalRoleRow.valid_until > at),
                PrincipalRoleRow.scope_type == scope_type,
                RoleRow.scope_type == scope_type,
                RoleRow.status == "active",
                PermissionRow.id == permission_id,
                PermissionRow.status == "active",
                PermissionRow.scope_type == scope_type,
                scope_match,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None


class SqlAlchemyAuthorizationAuditRepository:
    """
    Append-only authz audit. Uses an independent short transaction (M2) so deny
    decisions survive request rollback when ForbiddenError aborts the UoW.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session = session
        self._session_factory = session_factory

    async def append(
        self,
        *,
        principal_id: UUID | None,
        permission_code: str,
        scope_type: str,
        tenant_id: UUID | None,
        operator_org_id: UUID | None,
        decision: str,
        reason: str,
        request_id: str | None,
    ) -> None:
        row = AuthorizationAuditLogRow(
            id=uuid.uuid4(),
            principal_id=principal_id,
            permission_code=permission_code,
            scope_type=scope_type,
            tenant_id=tenant_id if scope_type == "tenant" else None,
            operator_org_id=operator_org_id if scope_type == "platform" else None,
            decision=decision,
            reason=reason,
            request_id=request_id,
        )
        if self._session_factory is not None:
            async with self._session_factory() as audit_session:
                audit_session.add(row)
                await audit_session.commit()
            return
        self._session.add(row)
        await self._session.flush()


def build_authorization_service(
    session: AsyncSession,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> "AuthorizationService":
    from authz.application.authorization_service import AuthorizationService

    return AuthorizationService(
        principals=SqlAlchemyPrincipalRepository(session),
        tenants=SqlAlchemyTenantAccessRepository(session),
        operators=SqlAlchemyOperatorAccessRepository(session),
        permissions=SqlAlchemyPermissionCatalogRepository(session),
        grants=SqlAlchemyRoleGrantRepository(session),
        audit=SqlAlchemyAuthorizationAuditRepository(session, session_factory=session_factory),
    )
