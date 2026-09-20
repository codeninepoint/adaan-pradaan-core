"""Idempotent seed helpers for permission catalog and system roles."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from authz.domain.catalog import (
    PLATFORM_SYSTEM_ROLE_PERMISSIONS,
    TENANT_SYSTEM_ROLE_PERMISSIONS,
    all_permission_specs,
    assert_role_may_receive_permission,
)
from authz.infrastructure.models import PermissionRow, RolePermissionRow, RoleRow


@dataclass(frozen=True, slots=True)
class SeedReport:
    permissions_upserted: int
    roles_upserted: int
    role_permissions_upserted: int


def seed_permission_catalog_sync(connection) -> int:
    """Upsert global permission catalog. Safe to rerun. Uses a sync DBAPI connection."""
    count = 0
    for spec in all_permission_specs():
        connection.execute(
            text(
                """
                INSERT INTO authz.permissions (id, code, scope_type, description, status)
                VALUES (gen_random_uuid(), :code, :scope_type, :description, 'active')
                ON CONFLICT (code) DO UPDATE SET
                  scope_type = EXCLUDED.scope_type,
                  description = COALESCE(EXCLUDED.description, authz.permissions.description),
                  status = 'active'
                """
            ),
            {
                "code": spec.code,
                "scope_type": spec.scope_type,
                "description": spec.description or None,
            },
        )
        count += 1
    return count


async def seed_permission_catalog(session: AsyncSession) -> int:
    count = 0
    for spec in all_permission_specs():
        existing = await session.execute(select(PermissionRow).where(PermissionRow.code == spec.code))
        row = existing.scalar_one_or_none()
        if row is None:
            session.add(
                PermissionRow(
                    id=uuid.uuid4(),
                    code=spec.code,
                    scope_type=spec.scope_type,
                    description=spec.description or None,
                    status="active",
                )
            )
        else:
            row.scope_type = spec.scope_type
            row.description = spec.description or row.description
            row.status = "active"
        count += 1
    await session.flush()
    return count


async def seed_tenant_system_roles(session: AsyncSession, tenant_id: UUID) -> SeedReport:
    """Ensure tenant-admin / resource-admin / viewer exist with catalog permissions."""
    await seed_permission_catalog(session)
    perm_rows = {
        p.code: p for p in (await session.execute(select(PermissionRow))).scalars().all()
    }
    roles_upserted = 0
    links_upserted = 0

    for role_name, codes in TENANT_SYSTEM_ROLE_PERMISSIONS.items():
        role = await _get_or_create_tenant_role(session, tenant_id=tenant_id, name=role_name)
        roles_upserted += 1
        for code in codes:
            assert_role_may_receive_permission(role_scope_type="tenant", permission_code=code)
            permission = perm_rows.get(code)
            if permission is None:
                continue
            if permission.scope_type != "tenant" or code.startswith("platform."):
                raise ValueError(
                    f"catalog inconsistency: {code} is not tenant-scoped but listed for {role_name}"
                )
            links_upserted += await _ensure_role_permission(session, role.id, permission.id)

    await session.flush()
    return SeedReport(
        permissions_upserted=len(all_permission_specs()),
        roles_upserted=roles_upserted,
        role_permissions_upserted=links_upserted,
    )


async def seed_platform_system_roles(session: AsyncSession, operator_org_id: UUID) -> SeedReport:
    """Ensure platform-admin / platform-support exist for an operator organization."""
    await seed_permission_catalog(session)
    perm_rows = {
        p.code: p for p in (await session.execute(select(PermissionRow))).scalars().all()
    }
    roles_upserted = 0
    links_upserted = 0

    for role_name, codes in PLATFORM_SYSTEM_ROLE_PERMISSIONS.items():
        role = await _get_or_create_platform_role(
            session, operator_org_id=operator_org_id, name=role_name
        )
        roles_upserted += 1
        for code in codes:
            assert_role_may_receive_permission(role_scope_type="platform", permission_code=code)
            permission = perm_rows.get(code)
            if permission is None:
                continue
            if permission.scope_type != "platform" or not code.startswith("platform."):
                raise ValueError(
                    f"catalog inconsistency: {code} is not platform-scoped but listed for {role_name}"
                )
            links_upserted += await _ensure_role_permission(session, role.id, permission.id)

    await session.flush()
    return SeedReport(
        permissions_upserted=len(all_permission_specs()),
        roles_upserted=roles_upserted,
        role_permissions_upserted=links_upserted,
    )


def seed_tenant_system_roles_sync(connection, tenant_id: UUID) -> None:
    """Sync variant for rare migration backfills; prefers async seed in app code."""
    seed_permission_catalog_sync(connection)
    for role_name, codes in TENANT_SYSTEM_ROLE_PERMISSIONS.items():
        for code in codes:
            assert_role_may_receive_permission(role_scope_type="tenant", permission_code=code)
        connection.execute(
            text(
                """
                INSERT INTO authz.roles (id, scope_type, tenant_id, operator_org_id, name, is_system_role, status)
                SELECT gen_random_uuid(), 'tenant', :tenant_id, NULL, :name, true, 'active'
                WHERE NOT EXISTS (
                  SELECT 1 FROM authz.roles
                  WHERE scope_type = 'tenant' AND tenant_id = :tenant_id AND name = :name
                )
                """
            ),
            {"tenant_id": str(tenant_id), "name": role_name},
        )
        connection.execute(
            text(
                """
                UPDATE authz.roles
                SET is_system_role = true, status = 'active'
                WHERE scope_type = 'tenant' AND tenant_id = :tenant_id AND name = :name
                """
            ),
            {"tenant_id": str(tenant_id), "name": role_name},
        )
        for code in codes:
            connection.execute(
                text(
                    """
                    INSERT INTO authz.role_permissions (id, role_id, permission_id)
                    SELECT gen_random_uuid(), r.id, p.id
                    FROM authz.roles r
                    JOIN authz.permissions p ON p.code = :code
                    WHERE r.scope_type = 'tenant'
                      AND r.tenant_id = :tenant_id
                      AND r.name = :name
                      AND p.scope_type = 'tenant'
                      AND p.code NOT LIKE 'platform.%'
                      AND NOT EXISTS (
                        SELECT 1 FROM authz.role_permissions rp
                        WHERE rp.role_id = r.id AND rp.permission_id = p.id
                      )
                    """
                ),
                {"tenant_id": str(tenant_id), "name": role_name, "code": code},
            )


async def _get_or_create_tenant_role(session: AsyncSession, *, tenant_id: UUID, name: str) -> RoleRow:
    result = await session.execute(
        select(RoleRow).where(
            RoleRow.scope_type == "tenant",
            RoleRow.tenant_id == tenant_id,
            RoleRow.name == name,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        role = RoleRow(
            id=uuid.uuid4(),
            scope_type="tenant",
            tenant_id=tenant_id,
            operator_org_id=None,
            name=name,
            is_system_role=True,
            status="active",
        )
        session.add(role)
        await session.flush()
    else:
        role.is_system_role = True
        role.status = "active"
    return role


async def _get_or_create_platform_role(
    session: AsyncSession, *, operator_org_id: UUID, name: str
) -> RoleRow:
    result = await session.execute(
        select(RoleRow).where(
            RoleRow.scope_type == "platform",
            RoleRow.operator_org_id == operator_org_id,
            RoleRow.name == name,
        )
    )
    role = result.scalar_one_or_none()
    if role is None:
        role = RoleRow(
            id=uuid.uuid4(),
            scope_type="platform",
            tenant_id=None,
            operator_org_id=operator_org_id,
            name=name,
            is_system_role=True,
            status="active",
        )
        session.add(role)
        await session.flush()
    else:
        role.is_system_role = True
        role.status = "active"
    return role


async def _ensure_role_permission(session: AsyncSession, role_id: UUID, permission_id: UUID) -> int:
    existing = await session.execute(
        select(RolePermissionRow).where(
            RolePermissionRow.role_id == role_id,
            RolePermissionRow.permission_id == permission_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return 0
    session.add(RolePermissionRow(id=uuid.uuid4(), role_id=role_id, permission_id=permission_id))
    return 1
