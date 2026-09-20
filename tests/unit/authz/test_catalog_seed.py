from __future__ import annotations

import pytest

from authz.domain.catalog import (
    PERMISSION_CATALOG,
    PLATFORM_SYSTEM_ROLE_PERMISSIONS,
    TENANT_SYSTEM_ROLE_PERMISSIONS,
    assert_role_may_receive_permission,
    scope_type_for_code,
)


def test_required_permission_codes_present() -> None:
    codes = {p.code for p in PERMISSION_CATALOG}
    assert codes == {
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
        "platform.tenant.read",
        "platform.tenant.suspend",
    }


def test_platform_codes_have_platform_scope() -> None:
    for spec in PERMISSION_CATALOG:
        assert spec.scope_type == scope_type_for_code(spec.code)


def test_tenant_roles_never_list_platform_permissions() -> None:
    for role_name, codes in TENANT_SYSTEM_ROLE_PERMISSIONS.items():
        for code in codes:
            assert_role_may_receive_permission(role_scope_type="tenant", permission_code=code)
            assert not code.startswith("platform."), role_name


def test_platform_roles_only_list_platform_permissions() -> None:
    for role_name, codes in PLATFORM_SYSTEM_ROLE_PERMISSIONS.items():
        for code in codes:
            assert_role_may_receive_permission(role_scope_type="platform", permission_code=code)
            assert code.startswith("platform."), role_name


def test_assert_blocks_cross_scope_attach() -> None:
    with pytest.raises(ValueError, match="platform permission"):
        assert_role_may_receive_permission(
            role_scope_type="tenant", permission_code="platform.tenant.read"
        )
    with pytest.raises(ValueError, match="tenant permission"):
        assert_role_may_receive_permission(
            role_scope_type="platform", permission_code="resource.read"
        )
