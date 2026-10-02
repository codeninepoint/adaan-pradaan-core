from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from authz.infrastructure.models import PrincipalRoleRow, RoleRow
from identity.domain.security import utcnow
from identity.infrastructure.models import AuditLogRow, UserRow
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import (
    OrgMembershipRow,
    OrganizationRow,
    TenantMembershipRow,
    TenantRow,
)


@dataclass(frozen=True, slots=True)
class TenantInviteResult:
    membership_id: UUID
    tenant_id: UUID
    user_id: UUID
    role: str
    status: str


@dataclass(frozen=True, slots=True)
class TenantRemoveResult:
    user_id: UUID
    tenant_id: UUID
    status: str


@dataclass(frozen=True, slots=True)
class OrgInviteResult:
    invite_id: UUID
    email: str
    org_role: str
    status: str
    user_id: UUID


@dataclass(frozen=True, slots=True)
class OrgRemoveResult:
    user_id: UUID
    status: str
    tenant_bindings_revoked: int


class MemberService:
    """J14 tenant invite/remove + J19 org invite/remove."""

    def __init__(self, session: AsyncSession, authorization: AuthorizationService) -> None:
        self._session = session
        self._authorization = authorization

    async def invite_tenant_member(
        self,
        *,
        tenant_id: UUID,
        caller_principal_id: UUID,
        user_id: UUID,
        role_name: str,
    ) -> TenantInviteResult:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")
        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None:
            raise NotFoundError("tenant not found")

        user = await self._session.get(UserRow, user_id)
        if user is None or user.status != "active":
            raise NotFoundError("user not found")

        org_member = (
            await self._session.execute(
                select(OrgMembershipRow.id).where(
                    OrgMembershipRow.organization_id == tenant.organization_id,
                    OrgMembershipRow.user_id == user_id,
                    OrgMembershipRow.status.in_(("active", "invited")),
                )
            )
        ).scalar_one_or_none()
        if org_member is None:
            raise NotFoundError("user not found or not an org member")

        existing = (
            await self._session.execute(
                select(TenantMembershipRow).where(
                    TenantMembershipRow.tenant_id == tenant_id,
                    TenantMembershipRow.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if existing and existing.status == "active":
            raise ConflictError("already a member of this tenant")

        role = (
            await self._session.execute(
                select(RoleRow).where(
                    RoleRow.tenant_id == tenant_id,
                    RoleRow.name == role_name,
                    RoleRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if role is None:
            raise ValidationError("unknown role")

        if existing:
            existing.status = "active"
            membership = existing
        else:
            membership = TenantMembershipRow(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user_id,
                status="active",
            )
            self._session.add(membership)

        now = utcnow()
        self._session.add(
            PrincipalRoleRow(
                id=uuid.uuid4(),
                principal_id=user.principal_id,
                role_id=role.id,
                scope_type="tenant",
                tenant_id=tenant_id,
                status="active",
                assigned_by=caller_principal_id,
                valid_from=now,
                created_at=now,
                justification="tenant member invite",
            )
        )

        caller = await self._user_for_principal(caller_principal_id)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="tenant_member.added",
                actor_user_id=caller.id if caller else None,
                tenant_id=tenant_id,
                payload_json={
                    "user_id": str(user_id),
                    "role": role_name,
                    "membership_id": str(membership.id),
                },
            )
        )
        await self._session.commit()
        return TenantInviteResult(
            membership_id=membership.id,
            tenant_id=tenant_id,
            user_id=user_id,
            role=role_name,
            status="active",
        )

    async def remove_tenant_member(
        self,
        *,
        tenant_id: UUID,
        caller_principal_id: UUID,
        user_id: UUID,
    ) -> TenantRemoveResult:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")
        membership = (
            await self._session.execute(
                select(TenantMembershipRow).where(
                    TenantMembershipRow.tenant_id == tenant_id,
                    TenantMembershipRow.user_id == user_id,
                    TenantMembershipRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise NotFoundError("not a member")

        admin_role = (
            await self._session.execute(
                select(RoleRow).where(
                    RoleRow.tenant_id == tenant_id,
                    RoleRow.name == "tenant-admin",
                    RoleRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if admin_role:
            user = await self._session.get(UserRow, user_id)
            if user:
                is_admin = (
                    await self._session.execute(
                        select(PrincipalRoleRow.id).where(
                            PrincipalRoleRow.principal_id == user.principal_id,
                            PrincipalRoleRow.role_id == admin_role.id,
                            PrincipalRoleRow.tenant_id == tenant_id,
                            PrincipalRoleRow.status == "active",
                        )
                    )
                ).scalar_one_or_none()
                if is_admin is not None:
                    admin_count = (
                        await self._session.execute(
                            select(func.count())
                            .select_from(PrincipalRoleRow)
                            .where(
                                PrincipalRoleRow.role_id == admin_role.id,
                                PrincipalRoleRow.tenant_id == tenant_id,
                                PrincipalRoleRow.status == "active",
                            )
                        )
                    ).scalar_one()
                    if admin_count <= 1:
                        raise ConflictError("cannot remove the last tenant-admin")

        membership.status = "removed"
        now = utcnow()
        user = await self._session.get(UserRow, user_id)
        if user:
            bindings = (
                await self._session.execute(
                    select(PrincipalRoleRow).where(
                        PrincipalRoleRow.tenant_id == tenant_id,
                        PrincipalRoleRow.status == "active",
                        PrincipalRoleRow.principal_id == user.principal_id,
                    )
                )
            ).scalars().all()
            for binding in bindings:
                binding.status = "revoked"
                binding.revoked_at = now

        caller = await self._user_for_principal(caller_principal_id)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="tenant_member.removed",
                actor_user_id=caller.id if caller else None,
                tenant_id=tenant_id,
                payload_json={"user_id": str(user_id)},
            )
        )
        await self._session.commit()
        return TenantRemoveResult(user_id=user_id, tenant_id=tenant_id, status="removed")

    async def invite_org_member(
        self,
        *,
        org_id: UUID,
        caller_user_id: UUID,
        email: str,
        org_role: str,
    ) -> OrgInviteResult:
        await self._require_org_owner(org_id, caller_user_id)
        email = email.strip().lower()
        if org_role not in ("member", "owner"):
            raise ValidationError("org_role must be member or owner")

        user = (
            await self._session.execute(
                select(UserRow).where(UserRow.normalized_email == email)
            )
        ).scalar_one_or_none()
        if user is None:
            raise NotFoundError("user not found — invitee must already have an account")

        existing = (
            await self._session.execute(
                select(OrgMembershipRow).where(
                    OrgMembershipRow.organization_id == org_id,
                    OrgMembershipRow.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if existing and existing.status in ("active", "invited"):
            raise ConflictError("already invited or already a member")

        if existing:
            existing.status = "invited"
            existing.role = org_role
            membership = existing
        else:
            membership = OrgMembershipRow(
                id=uuid.uuid4(),
                organization_id=org_id,
                user_id=user.id,
                role=org_role,
                status="invited",
            )
            self._session.add(membership)

        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="org_member.invited",
                actor_user_id=caller_user_id,
                payload_json={
                    "org_id": str(org_id),
                    "invite_id": str(membership.id),
                    "email": email,
                    "org_role": org_role,
                },
            )
        )
        await self._session.commit()
        return OrgInviteResult(
            invite_id=membership.id,
            email=email,
            org_role=org_role,
            status="invited",
            user_id=user.id,
        )

    async def accept_org_invite(
        self, *, org_id: UUID, caller_user_id: UUID
    ) -> OrgInviteResult:
        membership = (
            await self._session.execute(
                select(OrgMembershipRow).where(
                    OrgMembershipRow.organization_id == org_id,
                    OrgMembershipRow.user_id == caller_user_id,
                    OrgMembershipRow.status == "invited",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise NotFoundError("invite not found")
        membership.status = "active"
        user = await self._session.get(UserRow, caller_user_id)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="org_member.joined",
                actor_user_id=caller_user_id,
                payload_json={"org_id": str(org_id), "invite_id": str(membership.id)},
            )
        )
        await self._session.commit()
        return OrgInviteResult(
            invite_id=membership.id,
            email=user.email if user else "",
            org_role=membership.role,
            status="active",
            user_id=caller_user_id,
        )

    async def remove_org_member(
        self,
        *,
        org_id: UUID,
        caller_user_id: UUID,
        user_id: UUID,
    ) -> OrgRemoveResult:
        await self._require_org_owner(org_id, caller_user_id)
        if caller_user_id == user_id:
            raise ConflictError("cannot remove yourself")

        membership = (
            await self._session.execute(
                select(OrgMembershipRow).where(
                    OrgMembershipRow.organization_id == org_id,
                    OrgMembershipRow.user_id == user_id,
                    OrgMembershipRow.status.in_(("active", "invited")),
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise NotFoundError("member not found")

        membership.status = "removed"
        tenants = (
            await self._session.execute(
                select(TenantRow.id).where(TenantRow.organization_id == org_id)
            )
        ).scalars().all()
        revoked = 0
        now = utcnow()
        if tenants:
            user = await self._session.get(UserRow, user_id)
            if user:
                bindings = (
                    await self._session.execute(
                        select(PrincipalRoleRow).where(
                            PrincipalRoleRow.principal_id == user.principal_id,
                            PrincipalRoleRow.tenant_id.in_(tenants),
                            PrincipalRoleRow.status == "active",
                        )
                    )
                ).scalars().all()
                for binding in bindings:
                    binding.status = "revoked"
                    binding.revoked_at = now
                    revoked += 1
                for tid in tenants:
                    tm = (
                        await self._session.execute(
                            select(TenantMembershipRow).where(
                                TenantMembershipRow.tenant_id == tid,
                                TenantMembershipRow.user_id == user_id,
                                TenantMembershipRow.status == "active",
                            )
                        )
                    ).scalar_one_or_none()
                    if tm:
                        tm.status = "removed"

        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="org_member.removed",
                actor_user_id=caller_user_id,
                payload_json={
                    "org_id": str(org_id),
                    "user_id": str(user_id),
                    "tenant_bindings_revoked": revoked,
                },
            )
        )
        await self._session.commit()
        return OrgRemoveResult(
            user_id=user_id, status="removed", tenant_bindings_revoked=revoked
        )

    async def _require_org_owner(self, org_id: UUID, user_id: UUID) -> OrganizationRow:
        org = await self._session.get(OrganizationRow, org_id)
        if org is None:
            raise NotFoundError("organization not found")
        membership = (
            await self._session.execute(
                select(OrgMembershipRow).where(
                    OrgMembershipRow.organization_id == org_id,
                    OrgMembershipRow.user_id == user_id,
                    OrgMembershipRow.role == "owner",
                    OrgMembershipRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ForbiddenError("org owner required")
        return org

    async def _user_for_principal(self, principal_id: UUID) -> UserRow | None:
        return (
            await self._session.execute(select(UserRow).where(UserRow.principal_id == principal_id))
        ).scalar_one_or_none()

    async def _require(self, principal_id: UUID, tenant_id: UUID, permission: str) -> None:
        result = await self._authorization.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code=permission,
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
            )
        )
        if not result.allowed:
            raise ForbiddenError(public_forbid_detail(permission))
