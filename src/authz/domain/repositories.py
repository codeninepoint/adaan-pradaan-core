from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from authz.domain.models import PermissionRecord


class PrincipalRepository(Protocol):
    async def get_status(self, principal_id: UUID) -> str | None:
        """Return principal status or None if unknown."""


class TenantAccessRepository(Protocol):
    async def is_tenant_active(self, tenant_id: UUID) -> bool:
        """True when tenant exists and status is active."""

    async def has_active_tenant_membership(self, principal_id: UUID, tenant_id: UUID) -> bool:
        """Active TenantMembership (user) or matching active service account for tenant."""


class OperatorAccessRepository(Protocol):
    async def find_active_operator_org_id(self, principal_id: UUID) -> UUID | None:
        """
        Active org membership in an organization with is_platform_operator=true.
        Returns that organization id, or None.
        """


class PermissionCatalogRepository(Protocol):
    async def get_by_code(self, code: str) -> PermissionRecord | None:
        """Load permission catalog row by stable code."""


class RoleGrantRepository(Protocol):
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
        """
        True only when an active principal_roles row grants a role that:
        - matches the requested scope columns,
        - is active,
        - is within assignment validity window,
        - and role_permissions maps exactly to permission_id.
        """


class AuthorizationAuditRepository(Protocol):
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
        """Append-only authorization decision log."""
