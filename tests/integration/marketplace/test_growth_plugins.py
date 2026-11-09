from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.marketplace.test_platform_admin_governance import _operator
from tests.integration.resources.test_create_resource import register_verify_login


@pytest.mark.asyncio
async def test_growth_plugins_seed_configure_and_disable(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "growth-op@example.com")
    member = await register_verify_login(client, session_factory, "growth-member@example.com")
    member_headers = {"Authorization": f"Bearer {member.token}"}

    denied = await client.get("/api/v1/admin/growth-plugins", headers=member_headers)
    assert denied.status_code == 403, denied.text

    anon = await client.get("/api/v1/admin/growth-plugins")
    assert anon.status_code == 401, anon.text

    listed = await client.get("/api/v1/admin/growth-plugins", headers=op["headers"])
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert [item["key"] for item in body["items"]] == [
        "sales-pipeline",
        "digital-marketing",
        "publicity",
    ]
    assert body["summary"]["total_plugins"] == 3
    assert body["summary"]["total_modules"] == 18
    assert body["summary"]["enabled_plugins"] == 3

    sales = next(item for item in body["items"] if item["key"] == "sales-pipeline")
    assert sales["name"] == "Sales Pipeline"
    assert sales["group_label"] == "Sales"
    assert sales["lifecycle"] == "live"
    assert len(sales["modules"]) == 6
    assert sales["config"]["max_leads_per_vendor_month"] == 5000
    crm = next(module for module in sales["modules"] if module["key"] == "crm-export")
    assert crm["enabled"] is False
    assert crm["badge"] == "Beta"

    publicity = next(item for item in body["items"] if item["key"] == "publicity")
    assert publicity["lifecycle"] == "beta"
    tracker = next(module for module in publicity["modules"] if module["key"] == "pr-mention-tracker")
    assert tracker["enabled"] is False
    assert tracker["badge"] == "Soon"

    modules = [
        {**module, "enabled": True} if module["key"] == "crm-export" else module
        for module in sales["modules"]
    ]
    updated = await client.patch(
        "/api/v1/admin/growth-plugins/sales-pipeline",
        headers=op["headers"],
        json={
            "modules": modules,
            "config": {**sales["config"], "max_leads_per_vendor_month": 7500},
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["config"]["max_leads_per_vendor_month"] == 7500
    assert next(m for m in updated.json()["modules"] if m["key"] == "crm-export")["enabled"] is True

    reloaded = await client.get("/api/v1/admin/growth-plugins", headers=op["headers"])
    sales_after = next(item for item in reloaded.json()["items"] if item["key"] == "sales-pipeline")
    assert sales_after["config"]["max_leads_per_vendor_month"] == 7500

    disabled = await client.patch(
        "/api/v1/admin/growth-plugins/digital-marketing",
        headers=op["headers"],
        json={"enabled": False},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False

    after_disable = await client.get("/api/v1/admin/growth-plugins", headers=op["headers"])
    assert after_disable.json()["summary"]["enabled_plugins"] == 2

    bad_module = await client.patch(
        "/api/v1/admin/growth-plugins/sales-pipeline",
        headers=op["headers"],
        json={"modules": [{"key": "not-a-module", "label": "Nope", "enabled": True}]},
    )
    assert bad_module.status_code == 422, bad_module.text

    missing = await client.patch(
        "/api/v1/admin/growth-plugins/unknown-plugin",
        headers=op["headers"],
        json={"enabled": False},
    )
    assert missing.status_code == 404, missing.text
