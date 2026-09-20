from __future__ import annotations

from typing import Protocol
from uuid import UUID

from identity.application.ports.tenant_bootstrap import RegistrationBootstrapResult


class TenantBootstrapPort(Protocol):
    async def bootstrap_individual_org(
        self, *, user_id: UUID, principal_id: UUID, email: str, display_name: str
    ) -> RegistrationBootstrapResult: ...


class AuthzQueryPort(Protocol):
    async def has_tenant_permission(self, user_id: UUID, tenant_id: UUID, permission_code: str) -> bool: ...

    async def session_belongs_to_tenant(self, session_user_id: UUID, tenant_id: UUID) -> bool: ...
