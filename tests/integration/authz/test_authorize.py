from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from authz.domain.models import ApiSurface, AuthorizeCommand
from authz.infrastructure.models import (
    PermissionRow,
    PrincipalRoleRow,
    RolePermissionRow,
    RoleRow,
)
from authz.infrastructure.repositories import build_authorization_service
from identity.infrastructure.models import PrincipalRow, UserRow
from tenant.infrastructure.models import (
    OrgMembershipRow,
    OrganizationRow,
    TenantMembershipRow,
    TenantRow,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_principal_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    principal = PrincipalRow(id=uuid.uuid4(), principal_type="user", status="active")
    session.add(principal)
    await session.flush()
    user = UserRow(
        id=uuid.uuid4(),
        principal_id=principal.id,
        email=f"{principal.id}@example.com",
        normalized_email=f"{principal.id}@example.com",
        display_name="Tester",
        status="active",
    )
    session.add(user)
    await session.flush()
    return principal.id, user.id


async def _get_or_create_permission(
    session: AsyncSession, *, code: str, scope_type: str
) -> PermissionRow:
    existing = await session.execute(select(PermissionRow).where(PermissionRow.code == code))
    permission = existing.scalar_one_or_none()
    if permission is None:
        permission = PermissionRow(
            id=uuid.uuid4(), code=code, scope_type=scope_type, status="active"
        )
        session.add(permission)
        await session.flush()
    return permission


async def _seed_tenant_world(
    session: AsyncSession, *, user_id: uuid.UUID, principal_id: uuid.UUID, permission_code: str
) -> uuid.UUID:
    org = OrganizationRow(
        id=uuid.uuid4(),
        name="Acme",
        slug=f"acme-{uuid.uuid4().hex[:8]}",
        org_type="individual",
        participation="consumer",
        is_platform_operator=False,
    )
    session.add(org)
    await session.flush()
    tenant = TenantRow(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="default",
        slug=f"t-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    session.add(tenant)
    await session.flush()
    session.add(
        TenantMembershipRow(id=uuid.uuid4(), tenant_id=tenant.id, user_id=user_id, status="active")
    )

    permission = await _get_or_create_permission(
        session, code=permission_code, scope_type="tenant"
    )
    role = RoleRow(
        id=uuid.uuid4(),
        scope_type="tenant",
        tenant_id=tenant.id,
        name="tenant-admin",
        is_system_role=True,
        status="active",
    )
    session.add(role)
    await session.flush()
    session.add(RolePermissionRow(id=uuid.uuid4(), role_id=role.id, permission_id=permission.id))
    session.add(
        PrincipalRoleRow(
            id=uuid.uuid4(),
            principal_id=principal_id,
            role_id=role.id,
            scope_type="tenant",
            tenant_id=tenant.id,
            status="active",
            valid_from=_now() - timedelta(minutes=1),
        )
    )
    await session.commit()
    return tenant.id


@pytest.mark.asyncio
async def test_authorize_allows_tenant_permission(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        principal_id, user_id = await _seed_principal_user(session)
        tenant_id = await _seed_tenant_world(
            session, user_id=user_id, principal_id=principal_id, permission_code="tenant.admin"
        )

    async with session_factory() as session:
        svc = build_authorization_service(session)
        result = await svc.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code="tenant.admin",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
            )
        )
        assert result.allowed is True
        assert result.reason == "granted"


@pytest.mark.asyncio
async def test_authorize_public_rejects_platform_permission(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        principal_id, _ = await _seed_principal_user(session)
        await session.commit()
        svc = build_authorization_service(session)
        result = await svc.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code="platform.admin",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=uuid.uuid4(),
            )
        )
        assert result.allowed is False
        assert result.reason == "public_surface_rejects_platform_permission"


@pytest.mark.asyncio
async def test_authorize_management_rejects_tenant_permission(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        principal_id, _ = await _seed_principal_user(session)
        await session.commit()
        svc = build_authorization_service(session)
        result = await svc.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code="tenant.admin",
                api_surface=ApiSurface.MANAGEMENT,
            )
        )
        assert result.allowed is False
        assert result.reason == "management_surface_requires_platform_permission"


@pytest.mark.asyncio
async def test_authorize_denies_inactive_principal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        principal_id, user_id = await _seed_principal_user(session)
        tenant_id = await _seed_tenant_world(
            session, user_id=user_id, principal_id=principal_id, permission_code="resource.read"
        )
        principal = await session.get(PrincipalRow, principal_id)
        assert principal is not None
        principal.status = "locked"
        await session.commit()

    async with session_factory() as session:
        svc = build_authorization_service(session)
        result = await svc.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code="resource.read",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
            )
        )
        assert result.allowed is False
        assert result.reason == "principal_status_locked"


@pytest.mark.asyncio
async def test_authorize_denies_expired_assignment(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        principal_id, user_id = await _seed_principal_user(session)
        tenant_id = await _seed_tenant_world(
            session, user_id=user_id, principal_id=principal_id, permission_code="audit.read"
        )
        binding = (
            await session.execute(
                select(PrincipalRoleRow).where(PrincipalRoleRow.principal_id == principal_id)
            )
        ).scalar_one()
        binding.valid_until = _now() - timedelta(seconds=1)
        await session.commit()

    async with session_factory() as session:
        svc = build_authorization_service(session)
        result = await svc.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code="audit.read",
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
            )
        )
        assert result.allowed is False
        assert result.reason == "no_matching_role_permission"


@pytest.mark.asyncio
async def test_authorize_platform_requires_operator_membership(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        principal_id, _ = await _seed_principal_user(session)
        await _get_or_create_permission(session, code="platform.admin", scope_type="platform")
        await session.commit()

        svc = build_authorization_service(session)
        result = await svc.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code="platform.admin",
                api_surface=ApiSurface.MANAGEMENT,
            )
        )
        assert result.allowed is False
        assert result.reason == "operator_membership_inactive"


@pytest.mark.asyncio
async def test_authorize_platform_allow_with_operator_role(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        principal_id, user_id = await _seed_principal_user(session)
        org = OrganizationRow(
            id=uuid.uuid4(),
            name="Platform Ops",
            slug=f"ops-{uuid.uuid4().hex[:8]}",
            org_type="organization",
            participation="consumer",
            is_platform_operator=True,
            status="active",
        )
        session.add(org)
        await session.flush()
        session.add(
            OrgMembershipRow(
                id=uuid.uuid4(),
                organization_id=org.id,
                user_id=user_id,
                role="owner",
                status="active",
            )
        )
        permission = await _get_or_create_permission(
            session, code="platform.admin", scope_type="platform"
        )
        role = RoleRow(
            id=uuid.uuid4(),
            scope_type="platform",
            operator_org_id=org.id,
            name="platform-admin",
            is_system_role=True,
            status="active",
        )
        session.add(role)
        await session.flush()
        session.add(RolePermissionRow(id=uuid.uuid4(), role_id=role.id, permission_id=permission.id))
        session.add(
            PrincipalRoleRow(
                id=uuid.uuid4(),
                principal_id=principal_id,
                role_id=role.id,
                scope_type="platform",
                operator_org_id=org.id,
                status="active",
                valid_from=_now() - timedelta(minutes=1),
            )
        )
        await session.commit()
        operator_org_id = org.id

    async with session_factory() as session:
        svc = build_authorization_service(session)
        result = await svc.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code="platform.admin",
                api_surface=ApiSurface.MANAGEMENT,
            )
        )
        assert result.allowed is True
        assert result.operator_org_id == operator_org_id
