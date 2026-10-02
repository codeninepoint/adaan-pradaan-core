from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from authz.infrastructure.models import PrincipalRoleRow, RoleRow
from identity.domain.security import utcnow
from identity.infrastructure.models import AuditLogRow, PrincipalRow, UserRow
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import TenantMembershipRow


@dataclass(frozen=True, slots=True)
class RoleSummary:
    role_id: UUID
    name: str
    is_system_role: bool
    status: str


@dataclass(frozen=True, slots=True)
class BindingSummary:
    binding_id: UUID
    role_id: UUID
    role_name: str
    status: str
    granted_at: datetime
    expires_at: datetime | None
    justification: str | None


@dataclass(frozen=True, slots=True)
class MemberSummary:
    user_id: UUID
    principal_id: UUID
    email: str
    display_name: str
    membership_status: str
    bindings: list[BindingSummary]


@dataclass(frozen=True, slots=True)
class GrantResult:
    binding_id: UUID
    principal_id: UUID
    user_id: UUID | None
    role_id: UUID
    role_name: str
    status: str
    granted_by_principal_id: UUID
    granted_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class RevokeResult:
    binding_id: UUID
    status: str
    revoked_at: datetime
    effective: str


class RoleBindingService:
    """J10/J11 — grant and revoke tenant role bindings (principal_roles)."""

    def __init__(self, session: AsyncSession, authorization: AuthorizationService) -> None:
        self._session = session
        self._authorization = authorization

    async def list_roles(self, *, tenant_id: UUID, caller_principal_id: UUID) -> list[RoleSummary]:
        await self._require(caller_principal_id, tenant_id, "tenant.member.read")
        result = await self._session.execute(
            select(RoleRow)
            .where(
                RoleRow.tenant_id == tenant_id,
                RoleRow.scope_type == "tenant",
                RoleRow.status == "active",
            )
            .order_by(RoleRow.name)
        )
        return [
            RoleSummary(
                role_id=row.id,
                name=row.name,
                is_system_role=row.is_system_role,
                status=row.status,
            )
            for row in result.scalars().all()
        ]

    async def list_members(self, *, tenant_id: UUID, caller_principal_id: UUID) -> list[MemberSummary]:
        await self._require(caller_principal_id, tenant_id, "tenant.member.read")
        memberships = (
            await self._session.execute(
                select(TenantMembershipRow, UserRow)
                .join(UserRow, UserRow.id == TenantMembershipRow.user_id)
                .where(
                    TenantMembershipRow.tenant_id == tenant_id,
                    TenantMembershipRow.status == "active",
                )
                .order_by(UserRow.email)
            )
        ).all()

        members: list[MemberSummary] = []
        for membership, user in memberships:
            bindings = await self._active_bindings_for_principal(
                tenant_id=tenant_id, principal_id=user.principal_id
            )
            members.append(
                MemberSummary(
                    user_id=user.id,
                    principal_id=user.principal_id,
                    email=user.email,
                    display_name=user.display_name,
                    membership_status=membership.status,
                    bindings=bindings,
                )
            )
        return members

    async def grant(
        self,
        *,
        tenant_id: UUID,
        role_id: UUID,
        caller_principal_id: UUID,
        principal_id: UUID | None,
        user_id: UUID | None,
        expires_at: datetime | None,
        justification: str | None,
    ) -> GrantResult:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")

        if not principal_id and not user_id:
            raise ValidationError("principal_id or user_id is required")

        target_user: UserRow | None = None
        if user_id:
            target_user = await self._session.get(UserRow, user_id)
            if not target_user:
                raise NotFoundError("user not found")
            principal_id = target_user.principal_id
        else:
            assert principal_id is not None
            principal = await self._session.get(PrincipalRow, principal_id)
            if not principal or principal.status != "active":
                raise NotFoundError("principal not found")
            user_result = await self._session.execute(
                select(UserRow).where(UserRow.principal_id == principal_id)
            )
            target_user = user_result.scalar_one_or_none()

        role = await self._session.get(RoleRow, role_id)
        if not role or role.tenant_id != tenant_id or role.status != "active":
            raise NotFoundError("role not found in this tenant")
        if role.scope_type != "tenant":
            raise ValidationError("cannot assign platform-scope role in tenant context")

        if target_user:
            member = await self._session.execute(
                select(TenantMembershipRow.id).where(
                    TenantMembershipRow.tenant_id == tenant_id,
                    TenantMembershipRow.user_id == target_user.id,
                    TenantMembershipRow.status == "active",
                )
            )
            if member.scalar_one_or_none() is None:
                raise ValidationError("target user is not an active member of this tenant")

        existing = await self._session.execute(
            select(PrincipalRoleRow).where(
                PrincipalRoleRow.principal_id == principal_id,
                PrincipalRoleRow.role_id == role_id,
                PrincipalRoleRow.tenant_id == tenant_id,
                PrincipalRoleRow.status == "active",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ConflictError("user already has this role")

        now = utcnow()
        binding = PrincipalRoleRow(
            id=uuid4(),
            principal_id=principal_id,
            role_id=role.id,
            scope_type="tenant",
            tenant_id=tenant_id,
            status="active",
            assigned_by=caller_principal_id,
            valid_from=now,
            valid_until=expires_at,
            justification=justification,
            created_at=now,
        )
        self._session.add(binding)

        caller_user = (
            await self._session.execute(select(UserRow).where(UserRow.principal_id == caller_principal_id))
        ).scalar_one_or_none()
        self._session.add(
            AuditLogRow(
                id=uuid4(),
                event_action="role_binding.created",
                actor_user_id=caller_user.id if caller_user else None,
                tenant_id=tenant_id,
                payload_json={
                    "binding_id": str(binding.id),
                    "principal_id": str(principal_id),
                    "role_id": str(role.id),
                    "role_name": role.name,
                    "assigned_by": str(caller_principal_id),
                },
            )
        )
        await self._session.commit()
        return GrantResult(
            binding_id=binding.id,
            principal_id=principal_id,
            user_id=target_user.id if target_user else None,
            role_id=role.id,
            role_name=role.name,
            status="active",
            granted_by_principal_id=caller_principal_id,
            granted_at=now,
            expires_at=expires_at,
        )

    async def revoke(
        self,
        *,
        tenant_id: UUID,
        role_id: UUID,
        binding_id: UUID,
        caller_principal_id: UUID,
        reason: str | None,
    ) -> RevokeResult:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")

        binding = await self._session.get(PrincipalRoleRow, binding_id)
        if (
            binding is None
            or binding.tenant_id != tenant_id
            or binding.role_id != role_id
        ):
            raise NotFoundError("binding not found")
        if binding.status != "active":
            raise ConflictError("binding already revoked")

        role = await self._session.get(RoleRow, role_id)
        if role and role.name == "tenant-admin":
            active_admins = await self._count_active_tenant_admins(tenant_id)
            if active_admins <= 1:
                raise ConflictError("cannot revoke the last tenant-admin binding")

        now = utcnow()
        binding.status = "revoked"
        binding.revoked_at = now
        if reason:
            note = f"revoked: {reason}"
            binding.justification = (
                f"{binding.justification} | {note}" if binding.justification else note
            )

        caller_user = (
            await self._session.execute(select(UserRow).where(UserRow.principal_id == caller_principal_id))
        ).scalar_one_or_none()
        self._session.add(
            AuditLogRow(
                id=uuid4(),
                event_action="role_binding.revoked",
                actor_user_id=caller_user.id if caller_user else None,
                tenant_id=tenant_id,
                payload_json={
                    "binding_id": str(binding.id),
                    "principal_id": str(binding.principal_id),
                    "role_id": str(role_id),
                    "reason": reason,
                    "revoked_by": str(caller_principal_id),
                },
            )
        )
        await self._session.commit()
        return RevokeResult(
            binding_id=binding.id,
            status="revoked",
            revoked_at=now,
            effective="immediately",
        )

    async def _require(self, principal_id: UUID, tenant_id: UUID, permission: str) -> None:
        decision = await self._authorization.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code=permission,
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
            )
        )
        if not decision.allowed:
            raise ForbiddenError(public_forbid_detail(decision.reason))

    async def _active_bindings_for_principal(
        self, *, tenant_id: UUID, principal_id: UUID
    ) -> list[BindingSummary]:
        rows = (
            await self._session.execute(
                select(PrincipalRoleRow, RoleRow)
                .join(RoleRow, RoleRow.id == PrincipalRoleRow.role_id)
                .where(
                    PrincipalRoleRow.tenant_id == tenant_id,
                    PrincipalRoleRow.principal_id == principal_id,
                    PrincipalRoleRow.status == "active",
                )
                .order_by(RoleRow.name)
            )
        ).all()
        return [
            BindingSummary(
                binding_id=binding.id,
                role_id=role.id,
                role_name=role.name,
                status=binding.status,
                granted_at=binding.valid_from,
                expires_at=binding.valid_until,
                justification=binding.justification,
            )
            for binding, role in rows
        ]

    async def _count_active_tenant_admins(self, tenant_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(PrincipalRoleRow)
            .join(RoleRow, RoleRow.id == PrincipalRoleRow.role_id)
            .where(
                PrincipalRoleRow.tenant_id == tenant_id,
                PrincipalRoleRow.status == "active",
                RoleRow.name == "tenant-admin",
                RoleRow.tenant_id == tenant_id,
            )
        )
        return int(result.scalar_one() or 0)
