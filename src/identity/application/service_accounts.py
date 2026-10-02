from __future__ import annotations

import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from authz.infrastructure.models import PrincipalRoleRow, RoleRow
from identity.domain.security import hash_secret, utcnow
from identity.infrastructure.models import (
    ApiKeyRow,
    AuditLogRow,
    PrincipalRow,
    ServiceAccountRow,
    UserRow,
)
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import TenantRow

_SA_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")


@dataclass(frozen=True, slots=True)
class ServiceAccountCreated:
    service_account_id: UUID
    principal_id: UUID
    name: str
    api_key: str
    key_prefix: str
    key_id: UUID
    status: str
    role_assigned: str | None


@dataclass(frozen=True, slots=True)
class SaRoleAssigned:
    user_role_id: UUID
    principal_type: str
    role: str
    scope: str
    status: str


@dataclass(frozen=True, slots=True)
class ApiKeyRotated:
    old_key_prefix: str
    old_key_status: str
    new_api_key: str
    new_key_prefix: str
    new_key_id: UUID
    new_status: str


@dataclass(frozen=True, slots=True)
class ApiKeyRevoked:
    key_id: UUID
    key_prefix: str
    status: str
    revoked_at: datetime


@dataclass(frozen=True, slots=True)
class ServiceAccountSummary:
    service_account_id: UUID
    principal_id: UUID
    name: str
    description: str | None
    status: str
    key_prefix: str | None


def _generate_api_key() -> tuple[str, str]:
    prefix = f"ak_{secrets.token_hex(4)}"
    secret = secrets.token_urlsafe(24)
    return prefix, f"{prefix}_{secret}"


class ServiceAccountService:
    """J08–J09 — service accounts and API key lifecycle."""

    def __init__(self, session: AsyncSession, authorization: AuthorizationService) -> None:
        self._session = session
        self._authorization = authorization

    async def list(
        self, *, tenant_id: UUID, caller_principal_id: UUID
    ) -> list[ServiceAccountSummary]:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")
        rows = (
            await self._session.execute(
                select(ServiceAccountRow)
                .where(
                    ServiceAccountRow.tenant_id == tenant_id,
                    ServiceAccountRow.status == "active",
                )
                .order_by(ServiceAccountRow.name)
            )
        ).scalars().all()
        items: list[ServiceAccountSummary] = []
        for sa in rows:
            key = (
                await self._session.execute(
                    select(ApiKeyRow)
                    .where(
                        ApiKeyRow.service_account_id == sa.id,
                        ApiKeyRow.status == "active",
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            items.append(
                ServiceAccountSummary(
                    service_account_id=sa.id,
                    principal_id=sa.principal_id,
                    name=sa.name,
                    description=sa.description,
                    status=sa.status,
                    key_prefix=key.prefix if key else None,
                )
            )
        return items

    async def create(
        self,
        *,
        tenant_id: UUID,
        caller_principal_id: UUID,
        name: str,
        description: str | None,
        initial_role: str | None,
    ) -> ServiceAccountCreated:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")
        name = name.strip().lower()
        if not _SA_NAME_RE.match(name):
            raise ValidationError("invalid name")

        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None or tenant.status != "active":
            raise NotFoundError("tenant not found")

        dup = (
            await self._session.execute(
                select(ServiceAccountRow.id).where(
                    ServiceAccountRow.tenant_id == tenant_id,
                    ServiceAccountRow.name == name,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise ConflictError("SA name already exists in this tenant")

        principal = PrincipalRow(
            id=uuid.uuid4(),
            principal_type="service_account",
            status="active",
        )
        self._session.add(principal)
        await self._session.flush()

        sa = ServiceAccountRow(
            id=uuid.uuid4(),
            principal_id=principal.id,
            tenant_id=tenant_id,
            organization_id=tenant.organization_id,
            name=name,
            description=description,
            status="active",
            created_by_principal_id=caller_principal_id,
        )
        self._session.add(sa)
        await self._session.flush()

        prefix, raw_key = _generate_api_key()
        key = ApiKeyRow(
            id=uuid.uuid4(),
            service_account_id=sa.id,
            prefix=prefix,
            key_hash=hash_secret(raw_key),
            status="active",
        )
        self._session.add(key)

        role_assigned: str | None = None
        if initial_role:
            role = (
                await self._session.execute(
                    select(RoleRow).where(
                        RoleRow.tenant_id == tenant_id,
                        RoleRow.name == initial_role,
                        RoleRow.status == "active",
                    )
                )
            ).scalar_one_or_none()
            if role is None:
                raise NotFoundError("initial role not found")
            now = utcnow()
            self._session.add(
                PrincipalRoleRow(
                    id=uuid.uuid4(),
                    principal_id=principal.id,
                    role_id=role.id,
                    scope_type="tenant",
                    tenant_id=tenant_id,
                    status="active",
                    assigned_by=caller_principal_id,
                    valid_from=now,
                    created_at=now,
                    justification="initial role on SA create",
                )
            )
            role_assigned = role.name

        caller = await self._user_for_principal(caller_principal_id)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="service_account.created",
                actor_user_id=caller.id if caller else None,
                tenant_id=tenant_id,
                payload_json={
                    "service_account_id": str(sa.id),
                    "name": name,
                    "role_assigned": role_assigned,
                },
            )
        )
        await self._session.commit()
        return ServiceAccountCreated(
            service_account_id=sa.id,
            principal_id=principal.id,
            name=name,
            api_key=raw_key,
            key_prefix=prefix,
            key_id=key.id,
            status="active",
            role_assigned=role_assigned,
        )

    async def assign_role(
        self,
        *,
        tenant_id: UUID,
        sa_id: UUID,
        caller_principal_id: UUID,
        role_id: UUID,
        justification: str | None,
    ) -> SaRoleAssigned:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")
        sa = await self._get_sa(tenant_id, sa_id)
        role = await self._session.get(RoleRow, role_id)
        if not role or role.tenant_id != tenant_id or role.status != "active":
            raise NotFoundError("role not found")

        existing = (
            await self._session.execute(
                select(PrincipalRoleRow).where(
                    PrincipalRoleRow.principal_id == sa.principal_id,
                    PrincipalRoleRow.role_id == role.id,
                    PrincipalRoleRow.tenant_id == tenant_id,
                    PrincipalRoleRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("service account already has this role")

        now = utcnow()
        binding = PrincipalRoleRow(
            id=uuid.uuid4(),
            principal_id=sa.principal_id,
            role_id=role.id,
            scope_type="tenant",
            tenant_id=tenant_id,
            status="active",
            assigned_by=caller_principal_id,
            valid_from=now,
            created_at=now,
            justification=justification,
        )
        self._session.add(binding)
        caller = await self._user_for_principal(caller_principal_id)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="role_binding.created",
                actor_user_id=caller.id if caller else None,
                tenant_id=tenant_id,
                payload_json={
                    "binding_id": str(binding.id),
                    "principal_id": str(sa.principal_id),
                    "principal_type": "service_account",
                    "role_id": str(role.id),
                },
            )
        )
        await self._session.commit()
        return SaRoleAssigned(
            user_role_id=binding.id,
            principal_type="service_account",
            role=role.name,
            scope=f"tenant:{tenant_id}",
            status="active",
        )

    async def rotate_key(
        self,
        *,
        tenant_id: UUID,
        sa_id: UUID,
        caller_principal_id: UUID,
        reason: str | None,
    ) -> ApiKeyRotated:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")
        sa = await self._get_sa(tenant_id, sa_id)
        active = (
            await self._session.execute(
                select(ApiKeyRow).where(
                    ApiKeyRow.service_account_id == sa.id,
                    ApiKeyRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if active is None:
            raise ConflictError("no active key exists to rotate")

        now = utcnow()
        old_prefix = active.prefix
        active.status = "revoked"
        active.revoked_at = now

        prefix, raw_key = _generate_api_key()
        new_key = ApiKeyRow(
            id=uuid.uuid4(),
            service_account_id=sa.id,
            prefix=prefix,
            key_hash=hash_secret(raw_key),
            status="active",
        )
        self._session.add(new_key)

        caller = await self._user_for_principal(caller_principal_id)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="api_key.rotated",
                actor_user_id=caller.id if caller else None,
                tenant_id=tenant_id,
                payload_json={
                    "service_account_id": str(sa.id),
                    "old_key_id": str(active.id),
                    "new_key_id": str(new_key.id),
                    "reason": reason,
                },
            )
        )
        await self._session.commit()
        return ApiKeyRotated(
            old_key_prefix=old_prefix,
            old_key_status="revoked",
            new_api_key=raw_key,
            new_key_prefix=prefix,
            new_key_id=new_key.id,
            new_status="active",
        )

    async def revoke_key(
        self,
        *,
        tenant_id: UUID,
        sa_id: UUID,
        key_id: UUID,
        caller_principal_id: UUID,
        reason: str | None,
    ) -> ApiKeyRevoked:
        await self._require(caller_principal_id, tenant_id, "tenant.admin")
        sa = await self._get_sa(tenant_id, sa_id)
        key = await self._session.get(ApiKeyRow, key_id)
        if key is None or key.service_account_id != sa.id:
            raise NotFoundError("key not found")
        if key.status != "active":
            raise ConflictError("already revoked")

        now = utcnow()
        key.status = "revoked"
        key.revoked_at = now
        caller = await self._user_for_principal(caller_principal_id)
        self._session.add(
            AuditLogRow(
                id=uuid.uuid4(),
                event_action="api_key.revoked",
                actor_user_id=caller.id if caller else None,
                tenant_id=tenant_id,
                payload_json={
                    "service_account_id": str(sa.id),
                    "key_id": str(key.id),
                    "reason": reason,
                },
            )
        )
        await self._session.commit()
        return ApiKeyRevoked(
            key_id=key.id,
            key_prefix=key.prefix,
            status="revoked",
            revoked_at=now,
        )

    async def _get_sa(self, tenant_id: UUID, sa_id: UUID) -> ServiceAccountRow:
        sa = await self._session.get(ServiceAccountRow, sa_id)
        if sa is None or sa.tenant_id != tenant_id or sa.status != "active":
            raise NotFoundError("service account not found")
        return sa

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
