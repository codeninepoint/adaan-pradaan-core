"""Public deny reasons vs internal authz decision codes (M5)."""

from __future__ import annotations

# Internal AuthorizationService reasons → stable client-facing detail
PUBLIC_DENY_DETAIL = "forbidden"

INTERNAL_REASON_TO_PUBLIC: dict[str, str] = {
    "tenant_membership_inactive": "forbidden",
    "tenant_not_active": "forbidden",
    "no_matching_role_permission": "forbidden",
    "principal_not_found": "forbidden",
    "permission_not_found": "forbidden",
    "permission_not_active": "forbidden",
    "permission_scope_mismatch": "forbidden",
    "public_surface_rejects_platform_permission": "forbidden",
    "management_surface_requires_platform_permission": "forbidden",
    "operator_membership_inactive": "forbidden",
    "tenant_id_required": "forbidden",
    "permission_code_required": "forbidden",
}


def public_forbid_detail(internal_reason: str) -> str:
    if internal_reason.startswith("principal_status_"):
        return PUBLIC_DENY_DETAIL
    return INTERNAL_REASON_TO_PUBLIC.get(internal_reason, PUBLIC_DENY_DETAIL)
