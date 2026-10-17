"""Platform operator user directory and lifecycle actions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.ports.keycloak import KeycloakClient
from identity.domain.security import utcnow
from identity.infrastructure.models import (
    AuditLogRow,
    CredentialRow,
    IdentityRealmRow,
    PrincipalRow,
    ServiceAccountRow,
    SessionRow,
    UserRow,
)
from platform_ops.application.team_bootstrap import upsert_operator_team_member
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import (
    OrgMembershipRow,
    OrganizationRow,
    TenantMembershipRow,
    TenantRow,
)


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
class AdminUserItem:
    user_id: str
    principal_id: str
    email: str
    display_name: str
    principal_type: str
    status: str
    tenant_id: str | None
    tenant_name: str | None
    org_name: str | None
    role_label: str | None
    is_platform_operator: bool
    last_active_at: str | None


@dataclass(frozen=True, slots=True)
class AdminUserListResult:
    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int


class PlatformAdminUserService:
    def __init__(self, session: AsyncSession, keycloak: KeycloakClient) -> None:
        self._session = session
        self._keycloak = keycloak

    async def list_users(
        self,
        *,
        caller_user_id: UUID,
        q: str | None = None,
        principal_type: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AdminUserListResult:
        await _require_platform_operator(self._session, caller_user_id)
        if page < 1:
            raise ValidationError("page must be >= 1")
        if page_size < 1 or page_size > 200:
            raise ValidationError("page_size must be 1..200")
        if principal_type is not None and principal_type not in ("user", "service_account"):
            raise ValidationError("principal_type must be user or service_account")

        items: list[AdminUserItem] = []
        if principal_type in (None, "user"):
            items.extend(await self._list_human_users(q=q, status=status))
        if principal_type in (None, "service_account"):
            items.extend(await self._list_service_accounts(q=q, status=status))

        items.sort(key=lambda row: (row.email or "").lower())
        total = len(items)
        start = (page - 1) * page_size
        page_items = items[start : start + page_size]
        return AdminUserListResult(items=page_items, total=total, page=page, page_size=page_size)

    async def suspend_user(self, *, caller_user_id: UUID, target_user_id: UUID) -> dict:
        await _require_platform_operator(self._session, caller_user_id)
        user, principal = await self._require_user(target_user_id)
        if user.status == "blocked":
            raise ConflictError("user is blocked")
        user.status = "locked"
        principal.status = "locked"
        revoked = await self._revoke_sessions(user.id, caller_user_id)
        await self._audit("user.suspended", caller_user_id, {"user_id": str(user.id)})
        await self._session.commit()
        return {"user_id": str(user.id), "status": user.status, "sessions_revoked": revoked}

    async def reinstate_user(self, *, caller_user_id: UUID, target_user_id: UUID) -> dict:
        await _require_platform_operator(self._session, caller_user_id)
        user, principal = await self._require_user(target_user_id)
        if user.status == "blocked":
            raise ConflictError("blocked users cannot be reinstated")
        user.status = "active"
        principal.status = "active"
        await self._audit("user.reinstated", caller_user_id, {"user_id": str(user.id)})
        await self._session.commit()
        return {"user_id": str(user.id), "status": user.status}

    async def block_user(self, *, caller_user_id: UUID, target_user_id: UUID) -> dict:
        await _require_platform_operator(self._session, caller_user_id)
        user, principal = await self._require_user(target_user_id)
        user.status = "blocked"
        principal.status = "locked"
        revoked = await self._revoke_sessions(user.id, caller_user_id)
        await self._audit("user.blocked", caller_user_id, {"user_id": str(user.id)})
        await self._session.commit()
        return {"user_id": str(user.id), "status": user.status, "sessions_revoked": revoked}

    async def reset_mfa(self, *, caller_user_id: UUID, target_user_id: UUID) -> dict:
        await _require_platform_operator(self._session, caller_user_id)
        user, _principal = await self._require_user(target_user_id)
        cred = (
            await self._session.execute(
                select(CredentialRow, IdentityRealmRow)
                .join(IdentityRealmRow, IdentityRealmRow.id == CredentialRow.identity_realm_id)
                .where(CredentialRow.principal_id == user.principal_id)
                .limit(1)
            )
        ).first()
        if cred is None:
            raise NotFoundError("credential not found")
        credential, realm = cred
        await self._keycloak.reset_mfa(realm.realm_name, credential.keycloak_subject)
        await self._revoke_sessions(user.id, caller_user_id)
        await self._audit("user.mfa_reset", caller_user_id, {"user_id": str(user.id)})
        await self._session.commit()
        return {"user_id": str(user.id), "status": "mfa_reset_required"}

    async def promote_operator(self, *, caller_user_id: UUID, target_user_id: UUID) -> dict:
        await _require_platform_operator(self._session, caller_user_id)
        user, _principal = await self._require_user(target_user_id)
        memberships = (
            await self._session.execute(
                select(OrgMembershipRow, OrganizationRow)
                .join(OrganizationRow, OrganizationRow.id == OrgMembershipRow.organization_id)
                .where(
                    OrgMembershipRow.user_id == user.id,
                    OrgMembershipRow.status == "active",
                    OrgMembershipRow.role == "owner",
                )
            )
        ).all()
        if not memberships:
            raise ConflictError("target user has no owner organization membership")
        for _membership, org in memberships:
            org.is_platform_operator = True
        await upsert_operator_team_member(
            self._session,
            email=user.email,
            user_id=user.id,
            platform_role="platform_admin",
            invited_by=caller_user_id,
            status="active",
        )
        await self._audit(
            "user.promoted_operator",
            caller_user_id,
            {"user_id": str(user.id), "org_ids": [str(org.id) for _, org in memberships]},
        )
        await self._session.commit()
        return {"user_id": str(user.id), "is_platform_operator": True}

    async def _list_human_users(
        self, *, q: str | None, status: str | None
    ) -> list[AdminUserItem]:
        stmt = select(UserRow, PrincipalRow).join(
            PrincipalRow, PrincipalRow.id == UserRow.principal_id
        )
        if status:
            stmt = stmt.where(UserRow.status == status)
        if q:
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(UserRow.email).like(pattern),
                    func.lower(UserRow.display_name).like(pattern),
                    func.lower(UserRow.normalized_email).like(pattern),
                )
            )
        rows = (await self._session.execute(stmt.order_by(UserRow.created_at.desc()))).all()
        items: list[AdminUserItem] = []
        for user, principal in rows:
            tenant_id, tenant_name, org_name, role_label, is_op = await self._user_context(user.id)
            items.append(
                AdminUserItem(
                    user_id=str(user.id),
                    principal_id=str(principal.id),
                    email=user.email,
                    display_name=user.display_name,
                    principal_type="user",
                    status=user.status,
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    org_name=org_name,
                    role_label=role_label,
                    is_platform_operator=is_op,
                    last_active_at=user.last_login_at.isoformat() if user.last_login_at else None,
                )
            )
        return items

    async def _list_service_accounts(
        self, *, q: str | None, status: str | None
    ) -> list[AdminUserItem]:
        stmt = (
            select(ServiceAccountRow, PrincipalRow, TenantRow, OrganizationRow)
            .join(PrincipalRow, PrincipalRow.id == ServiceAccountRow.principal_id)
            .join(TenantRow, TenantRow.id == ServiceAccountRow.tenant_id)
            .join(OrganizationRow, OrganizationRow.id == ServiceAccountRow.organization_id)
        )
        if status:
            stmt = stmt.where(ServiceAccountRow.status == status)
        if q:
            pattern = f"%{q.strip().lower()}%"
            stmt = stmt.where(func.lower(ServiceAccountRow.name).like(pattern))
        rows = (await self._session.execute(stmt)).all()
        return [
            AdminUserItem(
                user_id=str(sa.id),
                principal_id=str(principal.id),
                email=f"sa:{sa.name}@{tenant.slug}",
                display_name=sa.name,
                principal_type="service_account",
                status=sa.status,
                tenant_id=str(tenant.id),
                tenant_name=tenant.name,
                org_name=org.name,
                role_label="service_account",
                is_platform_operator=False,
                last_active_at=None,
            )
            for sa, principal, tenant, org in rows
        ]

    async def _user_context(
        self, user_id: UUID
    ) -> tuple[str | None, str | None, str | None, str | None, bool]:
        tenant_row = (
            await self._session.execute(
                select(TenantMembershipRow, TenantRow)
                .join(TenantRow, TenantRow.id == TenantMembershipRow.tenant_id)
                .where(
                    TenantMembershipRow.user_id == user_id,
                    TenantMembershipRow.status == "active",
                )
                .limit(1)
            )
        ).first()
        org_row = (
            await self._session.execute(
                select(OrgMembershipRow, OrganizationRow)
                .join(OrganizationRow, OrganizationRow.id == OrgMembershipRow.organization_id)
                .where(
                    OrgMembershipRow.user_id == user_id,
                    OrgMembershipRow.status == "active",
                )
                .limit(1)
            )
        ).first()
        tenant_id = str(tenant_row[1].id) if tenant_row else None
        tenant_name = tenant_row[1].name if tenant_row else None
        org_name = org_row[1].name if org_row else None
        role_label = org_row[0].role if org_row else None
        is_op = bool(org_row[1].is_platform_operator) if org_row else False
        if is_op:
            role_label = "platform_operator"
        return tenant_id, tenant_name, org_name, role_label, is_op

    async def _require_user(self, user_id: UUID) -> tuple[UserRow, PrincipalRow]:
        user = await self._session.get(UserRow, user_id)
        if user is None:
            raise NotFoundError("user not found")
        principal = await self._session.get(PrincipalRow, user.principal_id)
        if principal is None:
            raise NotFoundError("principal not found")
        return user, principal

    async def _revoke_sessions(self, user_id: UUID, actor_user_id: UUID) -> int:
        sessions = (
            await self._session.execute(
                select(SessionRow).where(SessionRow.user_id == user_id, SessionRow.status == "active")
            )
        ).scalars().all()
        now = utcnow()
        for session in sessions:
            session.status = "revoked"
            session.revoked_at = now
            session.refresh_token_hash = None
        return len(sessions)

    async def _audit(self, action: str, actor_user_id: UUID, payload: dict) -> None:
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action=action,
                actor_user_id=actor_user_id,
                tenant_id=None,
                payload_json=payload,
            )
        )
