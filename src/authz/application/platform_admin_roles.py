"""Platform operator AuthZ catalog, roles matrix, custom roles, and bindings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.domain.catalog import (
    PLATFORM_SYSTEM_ROLE_PERMISSIONS,
    TENANT_SYSTEM_ROLE_PERMISSIONS,
    assert_role_may_receive_permission,
)
from authz.infrastructure.models import PermissionRow, PrincipalRoleRow, RolePermissionRow, RoleRow
from authz.infrastructure.seed import seed_permission_catalog
from identity.domain.security import utcnow
from identity.infrastructure.models import AuditLogRow, PrincipalRow, UserRow
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import OrgMembershipRow, OrganizationRow, TenantMembershipRow, TenantRow


async def _require_platform_operator(session: AsyncSession, user_id: UUID) -> None:
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


@dataclass(frozen=True, slots=True)
class PermissionView:
    code: str
    scope_type: str
    description: str | None


@dataclass(frozen=True, slots=True)
class RoleView:
    role_id: UUID | None
    name: str
    scope_type: str
    is_system_role: bool
    tenant_id: UUID | None
    operator_org_id: UUID | None
    status: str
    permission_codes: list[str]


@dataclass(frozen=True, slots=True)
class BindingView:
    binding_id: UUID
    principal_id: UUID
    user_email: str | None
    role_id: UUID
    role_name: str
    scope_type: str
    tenant_id: UUID | None
    tenant_name: str | None
    granted_by: UUID | None
    since: str
    status: str


class PlatformAdminRoleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_permissions(self, *, caller_user_id: UUID) -> list[PermissionView]:
        await _require_platform_operator(self._session, caller_user_id)
        await seed_permission_catalog(self._session)
        await self._session.flush()
        rows = (
            await self._session.execute(
                select(PermissionRow).where(PermissionRow.status == "active").order_by(PermissionRow.code)
            )
        ).scalars().all()
        return [
            PermissionView(code=row.code, scope_type=row.scope_type, description=row.description)
            for row in rows
        ]

    async def list_roles(self, *, caller_user_id: UUID) -> list[RoleView]:
        await _require_platform_operator(self._session, caller_user_id)
        await seed_permission_catalog(self._session)
        await self._session.flush()
        roles = (
            await self._session.execute(
                select(RoleRow).where(RoleRow.status == "active").order_by(RoleRow.scope_type, RoleRow.name)
            )
        ).scalars().all()
        # Prefer one representative system role per (scope, name) for the matrix.
        system_rep: dict[tuple[str, str], RoleView] = {}
        custom_views: list[RoleView] = []
        for role in roles:
            codes = await self._permission_codes(role.id)
            view = RoleView(
                role_id=role.id,
                name=role.name,
                scope_type=role.scope_type,
                is_system_role=role.is_system_role,
                tenant_id=role.tenant_id,
                operator_org_id=role.operator_org_id,
                status=role.status,
                permission_codes=codes,
            )
            if role.is_system_role:
                key = (role.scope_type, role.name)
                system_rep.setdefault(key, view)
            else:
                custom_views.append(view)

        for name, codes in TENANT_SYSTEM_ROLE_PERMISSIONS.items():
            system_rep.setdefault(
                ("tenant", name),
                RoleView(
                    role_id=None,
                    name=name,
                    scope_type="tenant",
                    is_system_role=True,
                    tenant_id=None,
                    operator_org_id=None,
                    status="template",
                    permission_codes=list(codes),
                ),
            )
        for name, codes in PLATFORM_SYSTEM_ROLE_PERMISSIONS.items():
            system_rep.setdefault(
                ("platform", name),
                RoleView(
                    role_id=None,
                    name=name,
                    scope_type="platform",
                    is_system_role=True,
                    tenant_id=None,
                    operator_org_id=None,
                    status="template",
                    permission_codes=list(codes),
                ),
            )
        return list(system_rep.values()) + custom_views

    async def list_bindings(self, *, caller_user_id: UUID) -> list[BindingView]:
        await _require_platform_operator(self._session, caller_user_id)
        rows = (
            await self._session.execute(
                select(PrincipalRoleRow, RoleRow, UserRow, TenantRow)
                .join(RoleRow, RoleRow.id == PrincipalRoleRow.role_id)
                .outerjoin(UserRow, UserRow.principal_id == PrincipalRoleRow.principal_id)
                .outerjoin(TenantRow, TenantRow.id == PrincipalRoleRow.tenant_id)
                .where(PrincipalRoleRow.status == "active")
                .order_by(PrincipalRoleRow.created_at.desc())
                .limit(500)
            )
        ).all()
        return [
            BindingView(
                binding_id=binding.id,
                principal_id=binding.principal_id,
                user_email=user.email if user else None,
                role_id=role.id,
                role_name=role.name,
                scope_type=binding.scope_type,
                tenant_id=binding.tenant_id,
                tenant_name=tenant.name if tenant else None,
                granted_by=binding.assigned_by,
                since=binding.valid_from.isoformat() if binding.valid_from else "",
                status=binding.status,
            )
            for binding, role, user, tenant in rows
        ]

    async def create_custom_role(
        self,
        *,
        caller_user_id: UUID,
        name: str,
        based_on: str,
        tenant_id: UUID,
        add_permissions: list[str],
        remove_permissions: list[str],
    ) -> RoleView:
        await _require_platform_operator(self._session, caller_user_id)
        name = name.strip()
        if not name:
            raise ValidationError("name is required")
        base_codes = TENANT_SYSTEM_ROLE_PERMISSIONS.get(based_on)
        if base_codes is None:
            raise ValidationError("based_on must be a tenant system role name")
        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None:
            raise NotFoundError("tenant not found")
        existing = (
            await self._session.execute(
                select(RoleRow.id).where(
                    RoleRow.tenant_id == tenant_id,
                    RoleRow.name == name,
                    RoleRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("role name already exists in tenant")

        await seed_permission_catalog(self._session)
        codes = set(base_codes)
        codes |= set(add_permissions)
        codes -= set(remove_permissions)
        for code in codes:
            assert_role_may_receive_permission(role_scope_type="tenant", permission_code=code)

        role = RoleRow(
            id=uuid.uuid4(),
            scope_type="tenant",
            tenant_id=tenant_id,
            operator_org_id=None,
            name=name,
            is_system_role=False,
            status="active",
        )
        self._session.add(role)
        await self._session.flush()
        perm_rows = {
            p.code: p
            for p in (await self._session.execute(select(PermissionRow))).scalars().all()
        }
        for code in sorted(codes):
            permission = perm_rows.get(code)
            if permission is None:
                raise ValidationError(f"unknown permission: {code}")
            self._session.add(
                RolePermissionRow(id=uuid.uuid4(), role_id=role.id, permission_id=permission.id)
            )
        await self._audit(
            caller_user_id,
            "custom_role.created",
            {"role_id": str(role.id), "tenant_id": str(tenant_id), "name": name},
        )
        await self._session.commit()
        return RoleView(
            role_id=role.id,
            name=role.name,
            scope_type=role.scope_type,
            is_system_role=False,
            tenant_id=role.tenant_id,
            operator_org_id=None,
            status=role.status,
            permission_codes=sorted(codes),
        )

    async def update_custom_role(
        self,
        *,
        caller_user_id: UUID,
        role_id: UUID,
        permission_codes: list[str],
    ) -> RoleView:
        await _require_platform_operator(self._session, caller_user_id)
        role = await self._session.get(RoleRow, role_id)
        if role is None or role.is_system_role or role.scope_type != "tenant":
            raise NotFoundError("custom role not found")
        await seed_permission_catalog(self._session)
        for code in permission_codes:
            assert_role_may_receive_permission(role_scope_type="tenant", permission_code=code)
        existing = (
            await self._session.execute(
                select(RolePermissionRow).where(RolePermissionRow.role_id == role_id)
            )
        ).scalars().all()
        for row in existing:
            await self._session.delete(row)
        await self._session.flush()
        perm_rows = {
            p.code: p
            for p in (await self._session.execute(select(PermissionRow))).scalars().all()
        }
        for code in permission_codes:
            permission = perm_rows.get(code)
            if permission is None:
                raise ValidationError(f"unknown permission: {code}")
            self._session.add(
                RolePermissionRow(id=uuid.uuid4(), role_id=role.id, permission_id=permission.id)
            )
        await self._audit(
            caller_user_id,
            "custom_role.updated",
            {"role_id": str(role.id), "permission_codes": permission_codes},
        )
        await self._session.commit()
        return RoleView(
            role_id=role.id,
            name=role.name,
            scope_type=role.scope_type,
            is_system_role=False,
            tenant_id=role.tenant_id,
            operator_org_id=role.operator_org_id,
            status=role.status,
            permission_codes=list(permission_codes),
        )

    async def grant_binding(
        self,
        *,
        caller_user_id: UUID,
        role_id: UUID,
        principal_id: UUID | None,
        user_id: UUID | None,
        tenant_id: UUID | None,
        justification: str | None,
    ) -> BindingView:
        await _require_platform_operator(self._session, caller_user_id)
        if not principal_id and not user_id:
            raise ValidationError("principal_id or user_id is required")
        role = await self._session.get(RoleRow, role_id)
        if role is None or role.status != "active":
            raise NotFoundError("role not found")

        target_user: UserRow | None = None
        if user_id:
            target_user = await self._session.get(UserRow, user_id)
            if target_user is None:
                raise NotFoundError("user not found")
            principal_id = target_user.principal_id
        assert principal_id is not None
        principal = await self._session.get(PrincipalRow, principal_id)
        if principal is None or principal.status != "active":
            raise NotFoundError("principal not found")

        if role.scope_type == "tenant":
            if tenant_id is None:
                raise ValidationError("tenant_id required for tenant role")
            if role.tenant_id != tenant_id:
                raise ValidationError("role does not belong to tenant")
            if target_user:
                member = (
                    await self._session.execute(
                        select(TenantMembershipRow.id).where(
                            TenantMembershipRow.tenant_id == tenant_id,
                            TenantMembershipRow.user_id == target_user.id,
                            TenantMembershipRow.status == "active",
                        )
                    )
                ).scalar_one_or_none()
                if member is None:
                    raise ValidationError("target user is not an active member of this tenant")
            scope_tenant_id = tenant_id
            operator_org_id = None
        else:
            if role.operator_org_id is None:
                raise ValidationError("platform role missing operator org")
            scope_tenant_id = None
            operator_org_id = role.operator_org_id

        existing = (
            await self._session.execute(
                select(PrincipalRoleRow).where(
                    PrincipalRoleRow.principal_id == principal_id,
                    PrincipalRoleRow.role_id == role_id,
                    PrincipalRoleRow.tenant_id == scope_tenant_id,
                    PrincipalRoleRow.operator_org_id == operator_org_id,
                    PrincipalRoleRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("binding already exists")

        caller = await self._session.get(UserRow, caller_user_id)
        now = utcnow()
        binding = PrincipalRoleRow(
            id=uuid.uuid4(),
            principal_id=principal_id,
            role_id=role.id,
            scope_type=role.scope_type,
            tenant_id=scope_tenant_id,
            operator_org_id=operator_org_id,
            status="active",
            assigned_by=caller.principal_id if caller else None,
            valid_from=now,
            justification=justification,
            created_at=now,
        )
        self._session.add(binding)
        await self._audit(
            caller_user_id,
            "role_binding.created",
            {
                "binding_id": str(binding.id),
                "principal_id": str(principal_id),
                "role_id": str(role.id),
                "tenant_id": str(scope_tenant_id) if scope_tenant_id else None,
            },
        )
        await self._session.commit()
        tenant = await self._session.get(TenantRow, scope_tenant_id) if scope_tenant_id else None
        return BindingView(
            binding_id=binding.id,
            principal_id=principal_id,
            user_email=target_user.email if target_user else None,
            role_id=role.id,
            role_name=role.name,
            scope_type=binding.scope_type,
            tenant_id=scope_tenant_id,
            tenant_name=tenant.name if tenant else None,
            granted_by=binding.assigned_by,
            since=now.isoformat(),
            status="active",
        )

    async def revoke_binding(
        self, *, caller_user_id: UUID, binding_id: UUID, reason: str | None = None
    ) -> dict:
        await _require_platform_operator(self._session, caller_user_id)
        binding = await self._session.get(PrincipalRoleRow, binding_id)
        if binding is None:
            raise NotFoundError("binding not found")
        if binding.status != "active":
            raise ConflictError("binding already revoked")
        now = utcnow()
        binding.status = "revoked"
        binding.revoked_at = now
        if reason:
            note = f"revoked: {reason}"
            binding.justification = (
                f"{binding.justification} | {note}" if binding.justification else note
            )
        await self._audit(
            caller_user_id,
            "role_binding.revoked",
            {"binding_id": str(binding.id), "reason": reason},
        )
        await self._session.commit()
        return {
            "binding_id": str(binding.id),
            "status": "revoked",
            "revoked_at": now.isoformat(),
        }

    async def _permission_codes(self, role_id: UUID) -> list[str]:
        rows = (
            await self._session.execute(
                select(PermissionRow.code)
                .join(RolePermissionRow, RolePermissionRow.permission_id == PermissionRow.id)
                .where(RolePermissionRow.role_id == role_id)
                .order_by(PermissionRow.code)
            )
        ).scalars().all()
        return list(rows)

    async def _audit(self, actor_user_id: UUID, action: str, payload: dict) -> None:
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action=action,
                actor_user_id=actor_user_id,
                tenant_id=None,
                payload_json=payload,
            )
        )
