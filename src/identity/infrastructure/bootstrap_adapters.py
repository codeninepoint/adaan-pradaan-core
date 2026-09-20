from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.domain.models import ApiSurface, AuthorizeCommand
from authz.infrastructure.models import PrincipalRoleRow, RoleRow
from authz.infrastructure.repositories import (
    SqlAlchemyTenantAccessRepository,
    build_authorization_service,
)
from authz.infrastructure.seed import seed_tenant_system_roles
from identity.application.ports.tenant_bootstrap import RegistrationBootstrapResult
from identity.infrastructure.models import UserRow
from shared.settings import settings
from tenant.infrastructure.models import (
    OrgMembershipRow,
    OrganizationRow,
    ProjectRow,
    TenantMembershipRow,
    TenantRow,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TenantBootstrapAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bootstrap_individual_org(
        self, *, user_id: UUID, principal_id: UUID, email: str, display_name: str
    ) -> RegistrationBootstrapResult:
        slug_base = re.sub(r"[^a-z0-9]+", "-", email.split("@")[0].lower()).strip("-") or "user"
        org_slug = f"{slug_base}-{str(user_id)[:8]}"
        org = OrganizationRow(
            id=uuid.uuid4(),
            name=f"{display_name} workspace",
            slug=org_slug,
            org_type="individual",
            participation="consumer",
            is_platform_operator=False,
        )
        self._session.add(org)
        await self._session.flush()

        membership = OrgMembershipRow(
            id=uuid.uuid4(),
            organization_id=org.id,
            user_id=user_id,
            role="owner",
        )
        self._session.add(membership)

        tenant = TenantRow(
            id=uuid.uuid4(),
            organization_id=org.id,
            name="default",
            slug=f"{slug_base}-default",
            status="active",
        )
        self._session.add(tenant)
        await self._session.flush()

        self._session.add(
            TenantMembershipRow(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user_id,
                status="active",
            )
        )

        project = ProjectRow(id=uuid.uuid4(), tenant_id=tenant.id, name="default-project")
        self._session.add(project)

        role_ids = await self._seed_roles(tenant.id)
        tenant_admin_role_id = role_ids["tenant-admin"]

        binding = PrincipalRoleRow(
            id=uuid.uuid4(),
            principal_id=principal_id,
            role_id=tenant_admin_role_id,
            scope_type="tenant",
            tenant_id=tenant.id,
            operator_org_id=None,
            status="active",
            assigned_by=principal_id,
        )
        self._session.add(binding)

        return RegistrationBootstrapResult(
            org_id=org.id,
            tenant_id=tenant.id,
            project_id=project.id,
            tenant_admin_role_id=tenant_admin_role_id,
        )

    async def _seed_roles(self, tenant_id: UUID) -> dict[str, UUID]:
        await seed_tenant_system_roles(self._session, tenant_id)
        result = await self._session.execute(
            select(RoleRow).where(RoleRow.scope_type == "tenant", RoleRow.tenant_id == tenant_id)
        )
        return {role.name: role.id for role in result.scalars().all()}


class AuthzReader:
    """Thin adapter for identity journeys; delegates to AuthorizationService (no JWT RBAC)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._authz: AuthorizationService = build_authorization_service(session)

    async def _principal_id_for_user(self, user_id: UUID) -> UUID | None:
        user = await self._session.get(UserRow, user_id)
        return user.principal_id if user else None

    async def has_tenant_permission(self, user_id: UUID, tenant_id: UUID, permission_code: str) -> bool:
        principal_id = await self._principal_id_for_user(user_id)
        if not principal_id:
            return False
        result = await self._authz.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code=permission_code,
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
            )
        )
        return result.allowed

    async def session_belongs_to_tenant(self, session_user_id: UUID, tenant_id: UUID) -> bool:
        principal_id = await self._principal_id_for_user(session_user_id)
        if not principal_id:
            return False
        return await SqlAlchemyTenantAccessRepository(self._session).has_active_tenant_membership(
            principal_id, tenant_id
        )


def generate_otp() -> str:
    from identity.domain.security import generate_otp as _generate_otp

    return _generate_otp()


def hash_secret(value: str) -> str:
    from identity.domain.security import hash_secret as _hash_secret

    return _hash_secret(value)


def verify_secret(value: str, hashed: str) -> bool:
    from identity.domain.security import verify_secret as _verify_secret

    return _verify_secret(value, hashed)


def utcnow() -> datetime:
    from identity.domain.security import utcnow as _utcnow

    return _utcnow()


def otp_expires_at() -> datetime:
    from identity.domain.security import otp_expires_at as _otp_expires_at

    return _otp_expires_at()


def refresh_expires_at() -> datetime:
    from identity.domain.security import refresh_expires_at as _refresh_expires_at

    return _refresh_expires_at()
