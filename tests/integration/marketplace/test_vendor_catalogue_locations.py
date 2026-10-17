from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_ops.infrastructure.models import PlatformConfigRow
from tests.integration.marketplace.test_platform_admin_governance import (
    _operator,
    _verified_vendor,
)
from tests.integration.resources.test_create_resource import register_verify_login


async def _seed_platform_config(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        session.add(
            PlatformConfigRow(key="product_content_review_required", value=True)
        )
        await session.commit()


def _listing_payload(city_id: str, *, product_id: str | None = None) -> dict:
    payload = {
        "name": "Organic Honey",
        "description": "Pure forest honey in glass jar.",
        "category": "Pantry",
        "sku": "HNY-500",
        "mrp_inr": 499.0,
        "net_weight": "500g",
        "brand": "Forest Gold",
        "image_urls": [
            "https://cdn.example.com/honey-1.jpg",
            "https://cdn.example.com/honey-2.jpg",
        ],
        "authenticity_attested": True,
        "city_ids": [city_id],
        "fulfilment_type": "SHIP_PHYSICAL",
    }
    if product_id is not None:
        payload["product_id"] = product_id
    return payload


@pytest.mark.asyncio
async def test_service_city_submit_approve_catalog_and_city_gate(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_platform_config(session_factory)
    op = await _operator(client, session_factory, "vc-loc-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "vc-loc-vendor@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    city = await client.post(
        f"/api/v1/vendors/{vendor_id}/service-cities",
        headers=headers,
        json={"city_name": "Mumbai"},
    )
    assert city.status_code == 201, city.text
    city_id = city.json()["city_id"]
    assert city.json()["warehouse_id"]

    pins = await client.put(
        f"/api/v1/vendors/{vendor_id}/service-cities/{city_id}/pincodes",
        headers=headers,
        json={"pincodes": ["400001", "400002"]},
    )
    assert pins.status_code == 200, pins.text
    assert pins.json()["pincodes"] == ["400001", "400002"]

    submitted = await client.post(
        f"/api/v1/vendors/{vendor_id}/products/submit",
        headers=headers,
        json=_listing_payload(city_id),
    )
    assert submitted.status_code == 201, submitted.text
    product_id = submitted.json()["product_id"]
    assert submitted.json()["pa_status"] == "pending_review"
    assert submitted.json()["visibility"] == "awaiting_pa"
    assert submitted.json()["cities"] == ["Mumbai"]
    assert submitted.json()["sku"] == "HNY-500"

    hidden = await client.get(f"/api/v1/marketplace/products/{product_id}")
    assert hidden.status_code == 404

    approve = await client.post(
        f"/api/v1/admin/products/{product_id}/approve",
        headers=op["headers"],
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["pa_status"] == "live"

    listed = await client.get(f"/api/v1/vendors/{vendor_id}/products", headers=headers)
    assert listed.status_code == 200, listed.text
    product = next(p for p in listed.json()["products"] if p["product_id"] == product_id)
    assert product["visibility"] == "visible"

    visible = await client.get(f"/api/v1/marketplace/products/{product_id}")
    assert visible.status_code == 200, visible.text

    catalog = await client.get("/api/v1/marketplace/catalog", params={"q": "Honey"})
    assert catalog.status_code == 200, catalog.text
    assert any(item["product_id"] == product_id for item in catalog.json()["results"])

    removed_city = await client.delete(
        f"/api/v1/vendors/{vendor_id}/service-cities/{city_id}",
        headers=headers,
    )
    assert removed_city.status_code == 204, removed_city.text

    hidden_again = await client.get(f"/api/v1/marketplace/products/{product_id}")
    assert hidden_again.status_code == 404

    assignments = await client.get(
        f"/api/v1/vendors/{vendor_id}/product-city-assignments", headers=headers
    )
    assert assignments.status_code == 200, assignments.text
    row = next(i for i in assignments.json()["items"] if i["product_id"] == product_id)
    assert row["status"] == "hidden"
    assert row["cities"] == []

    relisted = await client.get(f"/api/v1/vendors/{vendor_id}/products", headers=headers)
    product_after = next(
        p for p in relisted.json()["products"] if p["product_id"] == product_id
    )
    assert product_after["visibility"] == "hidden"


@pytest.mark.asyncio
async def test_reject_resubmit_and_inventory_by_city(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _seed_platform_config(session_factory)
    op = await _operator(client, session_factory, "vc-loc-op2@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "vc-loc-vendor2@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    city = await client.post(
        f"/api/v1/vendors/{vendor_id}/service-cities",
        headers=headers,
        json={"city_name": "Delhi"},
    )
    assert city.status_code == 201, city.text
    city_id = city.json()["city_id"]
    warehouse_id = city.json()["warehouse_id"]

    submitted = await client.post(
        f"/api/v1/vendors/{vendor_id}/products/submit",
        headers=headers,
        json=_listing_payload(city_id),
    )
    assert submitted.status_code == 201, submitted.text
    product_id = submitted.json()["product_id"]

    reject = await client.post(
        f"/api/v1/admin/products/{product_id}/reject",
        headers=op["headers"],
        json={"reason": "Images unclear"},
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["pa_status"] == "rejected"

    listed = await client.get(f"/api/v1/vendors/{vendor_id}/products", headers=headers)
    product = next(p for p in listed.json()["products"] if p["product_id"] == product_id)
    assert product["visibility"] == "hidden"
    assert product["pa_reject_reason"] == "Images unclear"

    resubmit = await client.post(
        f"/api/v1/products/{product_id}/resubmit",
        headers=headers,
    )
    assert resubmit.status_code == 200, resubmit.text
    assert resubmit.json()["pa_status"] == "pending_review"
    assert resubmit.json()["pa_reject_reason"] == ""
    assert resubmit.json()["visibility"] == "awaiting_pa"

    stock = await client.post(
        f"/api/v1/vendors/{vendor_id}/inventory",
        headers=headers,
        json={
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "sku": "HNY-500",
            "available": 5,
            "reorder_threshold": 10,
        },
    )
    assert stock.status_code == 201, stock.text

    by_city = await client.get(
        f"/api/v1/vendors/{vendor_id}/inventory",
        headers=headers,
        params={"view": "by_city"},
    )
    assert by_city.status_code == 200, by_city.text
    assert len(by_city.json()["city_rows"]) == 1
    row = by_city.json()["city_rows"][0]
    assert row["city_name"] == "Delhi"
    assert row["status"] == "low_stock"
    assert row["reorder_threshold"] == 10


@pytest.mark.asyncio
async def test_software_create_with_plugin_smoke(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "vc-loc-op3@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "vc-loc-vendor3@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    plugin = await client.post(
        f"/api/v1/vendors/{vendor_id}/plugins",
        headers=headers,
        json={
            "name": "Metrics Kit",
            "slug": "metrics-kit-vc",
            "category": "analytics",
            "short_description": "metrics",
        },
    )
    assert plugin.status_code == 201, plugin.text
    plugin_id = plugin.json()["plugin_id"]

    version = await client.post(
        f"/api/v1/plugins/{plugin_id}/versions",
        headers=headers,
        json={
            "version": "1.0.0",
            "artifact_url": "https://example.com/a.zip",
            "sbom_url": "https://example.com/sbom.json",
            "changelog": "init",
        },
    )
    assert version.status_code == 201, version.text
    version_id = version.json()["version_id"]
    caps = await client.put(
        f"/api/v1/plugins/versions/{version_id}/capabilities",
        headers=headers,
        json={"capabilities": [{"scope": "metrics.read", "justification": "read metrics"}]},
    )
    assert caps.status_code == 200, caps.text
    decide = await client.post(
        f"/api/v1/admin/plugin-reviews/{version_id}/decision",
        headers=op["headers"],
        json={"decision": "approved", "notes": "ok"},
    )
    assert decide.status_code == 200, decide.text

    product = await client.post(
        f"/api/v1/vendors/{vendor_id}/products",
        headers=headers,
        json={
            "name": "Metrics Suite",
            "description": "Software metrics",
            "plugin_id": plugin_id,
            "fulfilment_type": "PROVISION_SOFTWARE",
            "content": {"regions": ["ap-south-1"]},
        },
    )
    assert product.status_code == 201, product.text
    assert product.json()["fulfilment_type"] == "PROVISION_SOFTWARE"
