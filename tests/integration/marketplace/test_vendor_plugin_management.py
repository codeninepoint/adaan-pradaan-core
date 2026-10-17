from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.marketplace.test_platform_admin_governance import (
    _operator,
    _verified_vendor,
)
from tests.integration.resources.test_create_resource import register_verify_login


@pytest.mark.asyncio
async def test_vendor_standard_plugin_activate_deactivate(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "vpm-std-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "vpm-std-vendor@example.com", op["headers"]
    )

    created = await client.post(
        "/api/v1/admin/standard-plugins",
        headers=op["headers"],
        json={
            "name": "Basic Payments UPI",
            "slug": f"basic-payments-upi-{uuid.uuid4().hex[:8]}",
            "category": "SHIP_PHYSICAL",
            "short_description": "UPI payments",
            "version": "1.2.0",
            "artifact_url": "https://example.com/payments.zip",
            "publish": True,
        },
    )
    assert created.status_code == 201, created.text
    plugin_id = created.json()["plugin_id"]

    listed = await client.get(
        f"/api/v1/vendors/{vendor['vendor_id']}/standard-plugins",
        headers=vendor["headers"],
    )
    assert listed.status_code == 200, listed.text
    item = next(i for i in listed.json()["items"] if i["plugin_id"] == plugin_id)
    assert item["activation_status"] == "inactive"
    assert item["version"] == "1.2.0"

    activated = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/standard-plugins/{plugin_id}/activate",
        headers=vendor["headers"],
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["activation_status"] == "active"
    assert activated.json()["vendor_count"] >= 1

    deactivated = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/standard-plugins/{plugin_id}/deactivate",
        headers=vendor["headers"],
    )
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["activation_status"] == "inactive"

    other = await register_verify_login(client, session_factory, "vpm-std-other@example.com")
    forbidden = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/standard-plugins/{plugin_id}/activate",
        headers={"Authorization": f"Bearer {other.token}"},
    )
    assert forbidden.status_code in (401, 403)


@pytest.mark.asyncio
async def test_vendor_submit_reject_notes_and_resubmit(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "vpm-my-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "vpm-my-vendor@example.com", op["headers"]
    )

    submit = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/plugins/submit",
        headers=vendor["headers"],
        json={
            "name": "MyTax Custom",
            "version": "1.0.0",
            "category": "PROVISION_SOFTWARE",
            "description": "GST rules for my catalog",
            "artifact_url": "https://example.com/mytax.zip",
            "sbom_url": "",
        },
    )
    assert submit.status_code == 201, submit.text
    body = submit.json()
    assert body["status"] == "pending_review"
    plugin_id = body["plugin_id"]
    version_id = body["version_id"]

    listed = await client.get(
        f"/api/v1/vendors/{vendor['vendor_id']}/plugins",
        headers=vendor["headers"],
    )
    assert listed.status_code == 200, listed.text
    mine = next(p for p in listed.json()["plugins"] if p["plugin_id"] == plugin_id)
    assert mine["latest_version_status"] == "pending_review"

    claim = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/claim",
        headers=op["headers"],
    )
    assert claim.status_code == 200, claim.text
    reject = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/decision",
        headers=op["headers"],
        json={"decision": "rejected", "notes": "Use platform SMS plugin instead."},
    )
    assert reject.status_code == 200, reject.text

    listed2 = await client.get(
        f"/api/v1/vendors/{vendor['vendor_id']}/plugins",
        headers=vendor["headers"],
    )
    assert listed2.status_code == 200, listed2.text
    mine2 = next(p for p in listed2.json()["plugins"] if p["plugin_id"] == plugin_id)
    assert mine2["latest_version_status"] == "rejected"
    assert "SMS" in mine2["review_notes"] or "platform" in mine2["review_notes"].lower()

    resubmit = await client.post(
        f"/api/v1/vendors/{vendor['vendor_id']}/plugins/submit",
        headers=vendor["headers"],
        json={
            "plugin_id": plugin_id,
            "name": "MyTax Custom",
            "version": "1.1.0",
            "category": "PROVISION_SOFTWARE",
            "description": "Revised GST rules",
            "artifact_url": "https://example.com/mytax-v11.zip",
        },
    )
    assert resubmit.status_code == 201, resubmit.text
    assert resubmit.json()["status"] == "pending_review"
    assert resubmit.json()["version"] == "1.1.0"

    versions = await client.get(
        f"/api/v1/plugins/{plugin_id}/versions",
        headers=vendor["headers"],
    )
    assert versions.status_code == 200, versions.text
    assert any(v["version"] == "1.1.0" for v in versions.json()["versions"])
    rejected = next(v for v in versions.json()["versions"] if v["version"] == "1.0.0")
    assert rejected["review_notes"]
