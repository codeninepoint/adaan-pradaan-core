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


async def _seed_and_place_order(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    op_email: str,
    vendor_email: str,
    buyer_email: str,
    sku: str,
    mrp: float,
) -> dict:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, op_email)
    vendor = await _verified_vendor(client, session_factory, vendor_email, op["headers"])
    vendor_id = vendor["vendor_id"]
    headers = vendor["headers"]

    city = await client.post(
        f"/api/v1/vendors/{vendor_id}/service-cities",
        headers=headers,
        json={"city_name": "Mumbai"},
    )
    assert city.status_code == 201, city.text
    city_id = city.json()["city_id"]
    pins = await client.put(
        f"/api/v1/vendors/{vendor_id}/service-cities/{city_id}/pincodes",
        headers=headers,
        json={"pincodes": ["400001"]},
    )
    assert pins.status_code == 200, pins.text

    submitted = await client.post(
        f"/api/v1/vendors/{vendor_id}/products/submit",
        headers=headers,
        json={
            "name": "Return Test Milk",
            "description": "1L toned milk.",
            "category": "Dairy",
            "sku": sku,
            "mrp_inr": mrp,
            "net_weight": "1L",
            "brand": "TestBrand",
            "image_urls": [
                "https://cdn.example.com/milk-1.jpg",
                "https://cdn.example.com/milk-2.jpg",
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

    catalog = await client.get("/api/v1/marketplace/catalog", params={"q": "Return Test Milk"})
    card = next(item for item in catalog.json()["results"] if item["product_id"] == product_id)
    offering_id = card["offering_id"]

    buyer = await register_verify_login(client, session_factory, buyer_email)
    buyer_headers = {"Authorization": f"Bearer {buyer.token}"}
    buyer_tenant = str(buyer.tenant_id)

    cart = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/cart/lines",
        headers=buyer_headers,
        json={"offering_id": offering_id, "quantity": 1},
    )
    assert cart.status_code == 200, cart.text

    address = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/addresses",
        headers=buyer_headers,
        json={
            "label": "Home",
            "contact_name": "Return Buyer",
            "line1": "12 Link Road",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400001",
            "phone": "+919800011122",
        },
    )
    assert address.status_code == 201, address.text

    placed = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/orders",
        headers=buyer_headers,
        json={"address_id": address.json()["address_id"], "payment_method": "upi"},
    )
    assert placed.status_code == 201, placed.text
    order_id = placed.json()["order_id"]

    detail = await client.get(f"/api/v1/orders/{order_id}", headers=buyer_headers)
    assert detail.status_code == 200, detail.text
    line_id = detail.json()["lines"][0]["line_id"]

    opened = await client.post(
        f"/api/v1/orders/{order_id}/returns",
        headers=buyer_headers,
        json={"line_id": line_id, "reason": "Wrong item received"},
    )
    assert opened.status_code == 201, opened.text

    return {
        "vendor_id": vendor_id,
        "headers": headers,
        "return_id": opened.json()["return_id"],
        "mrp": mrp,
    }


@pytest.mark.asyncio
async def test_return_approve_then_refund(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    ctx = await _seed_and_place_order(
        client,
        session_factory,
        op_email="ret-appr-op@example.com",
        vendor_email="ret-appr-vendor@example.com",
        buyer_email="ret-appr-buyer@example.com",
        sku="RET-MILK-1",
        mrp=100.0,
    )
    vendor_id = ctx["vendor_id"]
    headers = ctx["headers"]
    return_id = ctx["return_id"]

    listed = await client.get(f"/api/v1/vendors/{vendor_id}/returns", headers=headers)
    assert listed.status_code == 200, listed.text
    row = next(r for r in listed.json()["returns"] if r["return_id"] == return_id)
    assert row["status"] == "requested"
    assert row["amount"] == 100.0
    assert row["currency"] == "INR"

    too_much = await client.patch(
        f"/api/v1/vendors/{vendor_id}/returns/{return_id}",
        headers=headers,
        json={"decision": "approved", "refund_amount": 999, "refund_method": "original"},
    )
    assert too_much.status_code == 422, too_much.text

    approved = await client.patch(
        f"/api/v1/vendors/{vendor_id}/returns/{return_id}",
        headers=headers,
        json={
            "decision": "approved",
            "refund_amount": 100,
            "refund_method": "original",
            "vendor_notes": "Confirmed wrong SKU",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["refund_amount"] == 100.0
    assert approved.json()["refund_method"] == "original"

    refunded = await client.post(
        f"/api/v1/vendors/{vendor_id}/returns/{return_id}/refund",
        headers=headers,
    )
    assert refunded.status_code == 200, refunded.text
    assert refunded.json()["status"] == "refunded"
    assert refunded.json()["refunded_at"]


@pytest.mark.asyncio
async def test_return_reject(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    ctx = await _seed_and_place_order(
        client,
        session_factory,
        op_email="ret-rej-op@example.com",
        vendor_email="ret-rej-vendor@example.com",
        buyer_email="ret-rej-buyer@example.com",
        sku="RET-MILK-2",
        mrp=80.0,
    )
    vendor_id = ctx["vendor_id"]
    headers = ctx["headers"]
    return_id = ctx["return_id"]

    rejected = await client.patch(
        f"/api/v1/vendors/{vendor_id}/returns/{return_id}",
        headers=headers,
        json={"decision": "rejected", "vendor_notes": "Outside return window"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"

    cannot_refund = await client.post(
        f"/api/v1/vendors/{vendor_id}/returns/{return_id}/refund",
        headers=headers,
    )
    assert cannot_refund.status_code == 409, cannot_refund.text
