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


@pytest.mark.asyncio
async def test_vendor_settings_default_currency_inr_and_patch(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "cur-settings-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "cur-settings-vendor@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    settings = await client.get(f"/api/v1/vendors/{vendor_id}/settings", headers=headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["default_currency"] == "INR"

    patched = await client.patch(
        f"/api/v1/vendors/{vendor_id}/settings",
        headers=headers,
        json={"default_currency": "USD"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["default_currency"] == "USD"

    again = await client.get(f"/api/v1/vendors/{vendor_id}/settings", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["default_currency"] == "USD"

    invalid = await client.patch(
        f"/api/v1/vendors/{vendor_id}/settings",
        headers=headers,
        json={"default_currency": "JPY"},
    )
    assert invalid.status_code == 422, invalid.text


@pytest.mark.asyncio
async def test_service_city_currency_override(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    op = await _operator(client, session_factory, "cur-city-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "cur-city-vendor@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    city = await client.post(
        f"/api/v1/vendors/{vendor_id}/service-cities",
        headers=headers,
        json={"city_name": "Dubai", "currency": "AED"},
    )
    assert city.status_code == 201, city.text
    assert city.json()["currency"] == "AED"
    assert city.json()["resolved_currency"] == "AED"

    listed = await client.get(f"/api/v1/vendors/{vendor_id}/service-cities", headers=headers)
    assert listed.status_code == 200, listed.text
    dubai = next(c for c in listed.json()["cities"] if c["city_name"] == "Dubai")
    assert dubai["currency"] == "AED"
    assert dubai["resolved_currency"] == "AED"

    cleared = await client.patch(
        f"/api/v1/vendors/{vendor_id}/service-cities/{city.json()['city_id']}",
        headers=headers,
        json={"currency": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["currency"] is None
    assert cleared.json()["resolved_currency"] == "INR"


@pytest.mark.asyncio
async def test_physical_listing_catalog_cart_order_currency_inr(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, "cur-flow-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "cur-flow-vendor@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]
    tenant_id = vendor["tenant_id"]

    city = await client.post(
        f"/api/v1/vendors/{vendor_id}/service-cities",
        headers=headers,
        json={"city_name": "Pune"},
    )
    assert city.status_code == 201, city.text
    city_id = city.json()["city_id"]

    pins = await client.put(
        f"/api/v1/vendors/{vendor_id}/service-cities/{city_id}/pincodes",
        headers=headers,
        json={"pincodes": ["411001"]},
    )
    assert pins.status_code == 200, pins.text

    submitted = await client.post(
        f"/api/v1/vendors/{vendor_id}/products/submit",
        headers=headers,
        json={
            "name": "Turmeric Powder",
            "description": "Organic turmeric 200g.",
            "category": "Spices",
            "sku": "TUR-200",
            "mrp_inr": 120.0,
            "net_weight": "200g",
            "brand": "SpiceCo",
            "image_urls": [
                "https://cdn.example.com/turmeric-1.jpg",
                "https://cdn.example.com/turmeric-2.jpg",
            ],
            "authenticity_attested": True,
            "city_ids": [city_id],
            "fulfilment_type": "SHIP_PHYSICAL",
        },
    )
    assert submitted.status_code == 201, submitted.text
    product_id = submitted.json()["product_id"]
    assert submitted.json()["currency"] == "INR"

    approve = await client.post(
        f"/api/v1/admin/products/{product_id}/approve",
        headers=op["headers"],
    )
    assert approve.status_code == 200, approve.text

    catalog = await client.get("/api/v1/marketplace/catalog", params={"q": "Turmeric"})
    assert catalog.status_code == 200, catalog.text
    card = next(item for item in catalog.json()["results"] if item["product_id"] == product_id)
    assert card["currency"] == "INR"
    assert card["price"] == 120.0
    assert card["price_usd"] == 120.0
    offering_id = card["offering_id"]

    buyer = await register_verify_login(client, session_factory, "cur-buyer@example.com")
    buyer_headers = {"Authorization": f"Bearer {buyer.token}"}
    buyer_tenant = str(buyer.tenant_id)

    cart = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/cart/lines",
        headers=buyer_headers,
        json={"offering_id": offering_id, "quantity": 1},
    )
    assert cart.status_code == 200, cart.text
    assert cart.json()["lines"][0]["currency"] == "INR"
    assert cart.json()["lines"][0]["unit_price"] == 120.0

    address = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/addresses",
        headers=buyer_headers,
        json={
            "label": "Home",
            "contact_name": "Buyer",
            "line1": "1 FC Road",
            "city": "Pune",
            "state": "MH",
            "pincode": "411001",
            "phone": "+919811112222",
        },
    )
    assert address.status_code == 201, address.text

    placed = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/orders",
        headers=buyer_headers,
        json={"address_id": address.json()["address_id"], "payment_method": "upi"},
    )
    assert placed.status_code == 201, placed.text

    detail = await client.get(
        f"/api/v1/orders/{placed.json()['order_id']}", headers=buyer_headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["lines"][0]["currency"] == "INR"
    assert detail.json()["lines"][0]["unit_price"] == 120.0
    assert tenant_id  # vendor has a tenant for portal auth
