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
async def test_vendor_reviews_create_and_list(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        session.add(PlatformConfigRow(key="product_content_review_required", value=True))
        await session.commit()

    op = await _operator(client, session_factory, "rev-op@example.com")
    vendor = await _verified_vendor(
        client, session_factory, "rev-vendor@example.com", op["headers"]
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
            "name": "Review Test Dahi",
            "description": "Fresh curd pack.",
            "category": "Dairy",
            "sku": "REV-DAHI-1",
            "mrp_inr": 60.0,
            "net_weight": "400g",
            "brand": "FreshCo",
            "image_urls": [
                "https://cdn.example.com/dahi-1.jpg",
                "https://cdn.example.com/dahi-2.jpg",
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

    catalog = await client.get("/api/v1/marketplace/catalog", params={"q": "Review Test Dahi"})
    card = next(item for item in catalog.json()["results"] if item["product_id"] == product_id)
    offering_id = card["offering_id"]

    buyer = await register_verify_login(client, session_factory, "rev-buyer@example.com")
    buyer_headers = {"Authorization": f"Bearer {buyer.token}"}
    buyer_tenant = str(buyer.tenant_id)

    address = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/addresses",
        headers=buyer_headers,
        json={
            "label": "Home",
            "contact_name": "Priya M.",
            "line1": "14 Marine Drive",
            "city": "Mumbai",
            "state": "MH",
            "pincode": "400001",
            "phone": "+919811122233",
        },
    )
    assert address.status_code == 201, address.text
    address_id = address.json()["address_id"]

    async def _place_and_get_line() -> tuple[str, str]:
        cart = await client.post(
            f"/api/v1/tenants/{buyer_tenant}/cart/lines",
            headers=buyer_headers,
            json={"offering_id": offering_id, "quantity": 1},
        )
        assert cart.status_code == 200, cart.text
        placed = await client.post(
            f"/api/v1/tenants/{buyer_tenant}/orders",
            headers=buyer_headers,
            json={"address_id": address_id, "payment_method": "upi"},
        )
        assert placed.status_code == 201, placed.text
        order_id = placed.json()["order_id"]
        detail = await client.get(f"/api/v1/orders/{order_id}", headers=buyer_headers)
        assert detail.status_code == 200, detail.text
        return order_id, detail.json()["lines"][0]["line_id"]

    order_a, line_a = await _place_and_get_line()
    order_b, line_b = await _place_and_get_line()

    created_a = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/reviews",
        headers=buyer_headers,
        json={
            "order_id": order_a,
            "line_id": line_a,
            "rating": 5,
            "comment": "Fresh and well-packed.",
        },
    )
    assert created_a.status_code == 201, created_a.text
    assert created_a.json()["rating"] == 5
    assert created_a.json()["product_name"] == "Review Test Dahi"

    created_b = await client.post(
        f"/api/v1/tenants/{buyer_tenant}/reviews",
        headers=buyer_headers,
        json={
            "order_id": order_b,
            "line_id": line_b,
            "rating": 4,
            "comment": "Good product.",
        },
    )
    assert created_b.status_code == 201, created_b.text

    listed = await client.get(f"/api/v1/vendors/{vendor_id}/reviews", headers=headers)
    assert listed.status_code == 200, listed.text
    reviews = listed.json()["reviews"]
    assert len(reviews) == 2
    by_rating = {row["rating"]: row for row in reviews}
    assert by_rating[5]["customer_name"] == "Priya M."
    assert by_rating[5]["product_name"] == "Review Test Dahi"
    assert by_rating[5]["comment"] == "Fresh and well-packed."
    assert by_rating[4]["comment"] == "Good product."

    # Stats rules (UI computes from list): avg 4.5, total 2, 4★+ 100%
    ratings = [row["rating"] for row in reviews]
    avg = round(sum(ratings) / len(ratings), 1)
    four_plus = round(100 * sum(1 for r in ratings if r >= 4) / len(ratings))
    assert avg == 4.5
    assert four_plus == 100
