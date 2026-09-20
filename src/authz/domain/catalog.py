"""Canonical permission catalog and system role templates (Prompt 5).

Seed operations must stay idempotent and must never attach platform.*
permissions to tenant-scoped roles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionSpec:
    code: str
    scope_type: str  # tenant | platform
    description: str = ""


# Required catalog (explicit Prompt 5 set).
PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("resource.read", "tenant", "List/read resources"),
    PermissionSpec("resource.create", "tenant", "Create resource records"),
    PermissionSpec("resource.update", "tenant", "Update resource records"),
    PermissionSpec("resource.delete", "tenant", "Delete resources"),
    PermissionSpec("tenant.member.read", "tenant", "List tenant members"),
    PermissionSpec("tenant.member.invite", "tenant", "Invite tenant members"),
    PermissionSpec("tenant.member.revoke", "tenant", "Revoke tenant membership"),
    PermissionSpec("tenant.settings.update", "tenant", "Update tenant settings"),
    PermissionSpec("vendor.read", "tenant", "Read vendor profile for tenant"),
    PermissionSpec("vendor.manage", "tenant", "Manage vendor settings for tenant"),
    PermissionSpec("billing.invoice.read", "tenant", "Read tenant invoices"),
    PermissionSpec("platform.tenant.read", "platform", "Read any tenant (management plane)"),
    PermissionSpec("platform.tenant.suspend", "platform", "Suspend a customer tenant"),
)

# Kept active so Phase 1 journeys / AuthzReader checks keep working.
COMPAT_PERMISSION_CATALOG: tuple[PermissionSpec, ...] = (
    PermissionSpec("tenant.admin", "tenant", "Legacy tenant admin (compat)"),
    PermissionSpec("resource.allocation.create", "tenant", "Legacy allocation create (compat)"),
    PermissionSpec("resource.allocation.approve", "tenant", "Legacy allocation approve (compat)"),
    PermissionSpec("audit.read", "tenant", "Legacy tenant audit read (compat)"),
)

TENANT_SYSTEM_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "tenant-admin": (
        "resource.read",
        "resource.create",
        "resource.update",
        "resource.delete",
        "tenant.member.read",
        "tenant.member.invite",
        "tenant.member.revoke",
        "tenant.settings.update",
        "vendor.read",
        "vendor.manage",
        "billing.invoice.read",
        "tenant.admin",
        "resource.allocation.create",
        "resource.allocation.approve",
        "audit.read",
    ),
    "resource-admin": (
        "resource.read",
        "resource.create",
        "resource.update",
        "resource.delete",
        "vendor.read",
        "vendor.manage",
        "resource.allocation.create",
        "resource.allocation.approve",
    ),
    "viewer": (
        "resource.read",
        "tenant.member.read",
        "vendor.read",
        "billing.invoice.read",
    ),
}

PLATFORM_SYSTEM_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "platform-admin": (
        "platform.tenant.read",
        "platform.tenant.suspend",
    ),
    "platform-support": (
        "platform.tenant.read",
    ),
}


def all_permission_specs() -> tuple[PermissionSpec, ...]:
    return PERMISSION_CATALOG + COMPAT_PERMISSION_CATALOG


def scope_type_for_code(code: str) -> str:
    if code.startswith("platform."):
        return "platform"
    return "tenant"


def assert_role_may_receive_permission(*, role_scope_type: str, permission_code: str) -> None:
    """Invariant: tenant roles never receive platform permissions."""
    perm_scope = scope_type_for_code(permission_code)
    if role_scope_type == "tenant" and (
        perm_scope == "platform" or permission_code.startswith("platform.")
    ):
        raise ValueError(
            f"refusing to attach platform permission {permission_code!r} to tenant-scoped role"
        )
    if role_scope_type == "platform" and perm_scope != "platform":
        raise ValueError(
            f"refusing to attach tenant permission {permission_code!r} to platform-scoped role"
        )
