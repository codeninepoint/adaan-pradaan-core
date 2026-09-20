from __future__ import annotations

from datetime import datetime, timezone

from authz.domain.models import (
    ApiSurface,
    AuthorizationDecision,
    AuthorizeCommand,
    AuthorizeResult,
)
from authz.domain.repositories import (
    AuthorizationAuditRepository,
    OperatorAccessRepository,
    PermissionCatalogRepository,
    PrincipalRepository,
    RoleGrantRepository,
    TenantAccessRepository,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthorizationService:
    """
    Default-deny authorization.

    Does not read roles or permissions from JWT. Callers pass principal_id and
    an explicit api_surface so public vs management route policy is enforced here.
    """

    def __init__(
        self,
        *,
        principals: PrincipalRepository,
        tenants: TenantAccessRepository,
        operators: OperatorAccessRepository,
        permissions: PermissionCatalogRepository,
        grants: RoleGrantRepository,
        audit: AuthorizationAuditRepository,
    ) -> None:
        self._principals = principals
        self._tenants = tenants
        self._operators = operators
        self._permissions = permissions
        self._grants = grants
        self._audit = audit

    async def authorize(self, command: AuthorizeCommand) -> AuthorizeResult:
        at = command.at or _utcnow()
        code = (command.permission_code or "").strip()

        if not code:
            return await self._deny(command, reason="permission_code_required", scope_type=None)

        if command.api_surface is ApiSurface.PUBLIC:
            if code.startswith("platform."):
                return await self._deny(
                    command,
                    reason="public_surface_rejects_platform_permission",
                    scope_type="platform",
                )
            return await self._authorize_tenant(command, code=code, at=at)

        if command.api_surface is ApiSurface.MANAGEMENT:
            if not code.startswith("platform."):
                return await self._deny(
                    command,
                    reason="management_surface_requires_platform_permission",
                    scope_type="tenant",
                )
            return await self._authorize_platform(command, code=code, at=at)

        return await self._deny(command, reason="unknown_api_surface", scope_type=None)

    async def _authorize_tenant(
        self, command: AuthorizeCommand, *, code: str, at: datetime
    ) -> AuthorizeResult:
        if command.tenant_id is None:
            return await self._deny(command, reason="tenant_id_required", scope_type="tenant")

        status = await self._principals.get_status(command.principal_id)
        if status is None:
            return await self._deny(
                command, reason="principal_not_found", scope_type="tenant", tenant_id=command.tenant_id
            )
        if status != "active":
            return await self._deny(
                command,
                reason=f"principal_status_{status}",
                scope_type="tenant",
                tenant_id=command.tenant_id,
            )

        if not await self._tenants.is_tenant_active(command.tenant_id):
            return await self._deny(
                command, reason="tenant_not_active", scope_type="tenant", tenant_id=command.tenant_id
            )

        if not await self._tenants.has_active_tenant_membership(
            command.principal_id, command.tenant_id
        ):
            return await self._deny(
                command,
                reason="tenant_membership_inactive",
                scope_type="tenant",
                tenant_id=command.tenant_id,
            )

        permission = await self._permissions.get_by_code(code)
        if permission is None:
            return await self._deny(
                command, reason="permission_not_found", scope_type="tenant", tenant_id=command.tenant_id
            )
        if permission.status != "active":
            return await self._deny(
                command,
                reason="permission_not_active",
                scope_type="tenant",
                tenant_id=command.tenant_id,
            )
        if permission.scope_type != "tenant":
            return await self._deny(
                command,
                reason="permission_scope_mismatch",
                scope_type=permission.scope_type,
                tenant_id=command.tenant_id,
            )

        granted = await self._grants.has_exact_permission_grant(
            principal_id=command.principal_id,
            permission_id=permission.id,
            scope_type="tenant",
            tenant_id=command.tenant_id,
            operator_org_id=None,
            at=at,
        )
        if not granted:
            return await self._deny(
                command,
                reason="no_matching_role_permission",
                scope_type="tenant",
                tenant_id=command.tenant_id,
            )

        return await self._allow(
            command, reason="granted", scope_type="tenant", tenant_id=command.tenant_id
        )

    async def _authorize_platform(
        self, command: AuthorizeCommand, *, code: str, at: datetime
    ) -> AuthorizeResult:
        status = await self._principals.get_status(command.principal_id)
        if status is None:
            return await self._deny(command, reason="principal_not_found", scope_type="platform")
        if status != "active":
            return await self._deny(
                command, reason=f"principal_status_{status}", scope_type="platform"
            )

        operator_org_id = command.operator_org_id
        if operator_org_id is None:
            operator_org_id = await self._operators.find_active_operator_org_id(command.principal_id)
        else:
            discovered = await self._operators.find_active_operator_org_id(command.principal_id)
            if discovered is None or discovered != operator_org_id:
                return await self._deny(
                    command,
                    reason="operator_membership_inactive",
                    scope_type="platform",
                    operator_org_id=operator_org_id,
                )

        if operator_org_id is None:
            return await self._deny(
                command, reason="operator_membership_inactive", scope_type="platform"
            )

        permission = await self._permissions.get_by_code(code)
        if permission is None:
            return await self._deny(
                command,
                reason="permission_not_found",
                scope_type="platform",
                operator_org_id=operator_org_id,
            )
        if permission.status != "active":
            return await self._deny(
                command,
                reason="permission_not_active",
                scope_type="platform",
                operator_org_id=operator_org_id,
            )
        if permission.scope_type != "platform":
            return await self._deny(
                command,
                reason="permission_scope_mismatch",
                scope_type=permission.scope_type,
                operator_org_id=operator_org_id,
            )
        if not permission.code.startswith("platform."):
            return await self._deny(
                command,
                reason="permission_code_not_platform",
                scope_type="platform",
                operator_org_id=operator_org_id,
            )

        granted = await self._grants.has_exact_permission_grant(
            principal_id=command.principal_id,
            permission_id=permission.id,
            scope_type="platform",
            tenant_id=None,
            operator_org_id=operator_org_id,
            at=at,
        )
        if not granted:
            return await self._deny(
                command,
                reason="no_matching_role_permission",
                scope_type="platform",
                operator_org_id=operator_org_id,
            )

        return await self._allow(
            command,
            reason="granted",
            scope_type="platform",
            operator_org_id=operator_org_id,
        )

    async def _allow(
        self,
        command: AuthorizeCommand,
        *,
        reason: str,
        scope_type: str,
        tenant_id=None,
        operator_org_id=None,
    ) -> AuthorizeResult:
        result = AuthorizeResult(
            allowed=True,
            decision=AuthorizationDecision.ALLOW,
            reason=reason,
            permission_code=command.permission_code,
            scope_type=scope_type,
            tenant_id=tenant_id if tenant_id is not None else command.tenant_id,
            operator_org_id=operator_org_id if operator_org_id is not None else command.operator_org_id,
        )
        await self._audit.append(
            principal_id=command.principal_id,
            permission_code=command.permission_code,
            scope_type=scope_type,
            tenant_id=result.tenant_id,
            operator_org_id=result.operator_org_id,
            decision=result.decision.value,
            reason=reason,
            request_id=command.request_id,
        )
        return result

    async def _deny(
        self,
        command: AuthorizeCommand,
        *,
        reason: str,
        scope_type: str | None,
        tenant_id=None,
        operator_org_id=None,
    ) -> AuthorizeResult:
        resolved_scope = scope_type or (
            "platform" if command.api_surface is ApiSurface.MANAGEMENT else "tenant"
        )
        result = AuthorizeResult(
            allowed=False,
            decision=AuthorizationDecision.DENY,
            reason=reason,
            permission_code=command.permission_code,
            scope_type=resolved_scope,
            tenant_id=tenant_id if tenant_id is not None else command.tenant_id,
            operator_org_id=operator_org_id if operator_org_id is not None else command.operator_org_id,
        )
        await self._audit.append(
            principal_id=command.principal_id,
            permission_code=command.permission_code or "",
            scope_type=resolved_scope,
            tenant_id=result.tenant_id,
            operator_org_id=result.operator_org_id,
            decision=result.decision.value,
            reason=reason,
            request_id=command.request_id,
        )
        return result
