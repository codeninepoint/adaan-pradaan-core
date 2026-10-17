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
async def test_vendor_customers_enriched_row(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, "cust-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "cust-vendor@example.com", op["headers"]
    )
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

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
            "name": "Customer Test Snack",
            "description": "Crunchy snack pack.",
            "category": "Snacks",
            "sku": "CUST-SNK-1",
            "mrp_inr": 240.0,
            "net_weight": "100g",
            "brand": "SnackCo",
            "image_urls": [
                "https://cdn.example.com/snack-1.jpg",
                "https://cdn.example.com/snack-2.jpg",
            ],
            "authenticity_attested": True,
            "city_ids": [city_id],
            "fulfilment_type": "SHIP_PHYSICAL",
        },
    )
    assert submitted.status_code == 201, submitted.text
    product_id = submitted.json()["product_id"]
    approve = await client.post(
        f"/api/v1/admin/products/{product_id}/approve",
        headers=op["headers"],
    )
    assert approve.status_code == 200, approve.text

    catalog = await client.get("/api/v1/marketplace/catalog", params={"q": "Customer Test Snack"})
    card = next(item for item in catalog.json()["results"] if item["product_id"] == product_id)

    buyer = await register_verify_login(client, session_factory, "cust-buyer@example.com")
    buyer_headers = {"Authorization": f"Bearer {buyer.token}"}
    buyer_tenant = str(buyer.tenant_id)

    cart = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/cart/lines",
        headers=buyer_headers,
        json={"offering_id": card["offering_id"], "quantity": 1},
    )
    assert cart.status_code == 200, cart.text

    address = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/addresses",
        headers=buyer_headers,
        json={
            "label": "Home",
            "contact_name": "Vanu Thakur",
            "line1": "9 FC Road",
            "city": "Pune",
            "state": "MH",
            "pincode": "411001",
            "phone": "+919811100011",
        },
    )
    assert address.status_code == 201, address.text

    placed = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/orders",
        headers=buyer_headers,
        json={"address_id": address.json()["address_id"], "payment_method": "upi"},
    )
    assert placed.status_code == 201, placed.text

    customers = await client.get(f"/api/v1/vendors/{vendor_id}/customers", headers=headers)
    assert customers.status_code == 200, customers.text
    rows = customers.json()["customers"]
    assert len(rows) >= 1
    row = next(item for item in rows if item["customer_name"] == "Vanu Thakur")
    assert row["city"] == "Pune"
    assert row["currency"] == "INR"
    assert row["segment"] == "New"
    assert row["order_count"] == 1
    assert row["total"] == 240.0
