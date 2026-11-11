import pytest
from decimal import Decimal

from payments.application.cashfree_client import StubPaymentProvider


@pytest.mark.asyncio
async def test_stub_create_order_returns_session():
    provider = StubPaymentProvider()
    created = await provider.create_order(
        merchant_order_id="ap_testorder123",
        amount=Decimal("199.00"),
        currency="INR",
        customer_id="user-1",
        customer_email="a@example.com",
        customer_phone="9876543210",
        customer_name="Ada",
        return_url="http://localhost:3000/return",
        notify_url="http://localhost:8000/api/v1/webhooks/cashfree/payments",
        payment_methods="upi",
        idempotency_key="idem-1",
    )
    assert created.payment_session_id.startswith("stub_session_")
    assert created.merchant_order_id == "ap_testorder123"
    assert created.order_status == "ACTIVE"


@pytest.mark.asyncio
async def test_stub_create_refund_success():
    provider = StubPaymentProvider()
    refund = await provider.create_refund(
        merchant_order_id="ap_testorder123",
        refund_id="rf_abc",
        amount=Decimal("50"),
        reason="return",
        idempotency_key="idem-r1",
    )
    assert refund.status == "SUCCESS"
    assert refund.cf_refund_id.startswith("stub_refund_")
