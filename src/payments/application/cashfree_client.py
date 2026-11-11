"""Cashfree PG HTTP client + offline stub."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

import httpx

from shared.domain.exceptions import ValidationError
from shared.settings import settings


@dataclass(frozen=True, slots=True)
class CreatedOrder:
    merchant_order_id: str
    cf_order_id: str
    payment_session_id: str
    order_status: str
    raw: dict


@dataclass(frozen=True, slots=True)
class CreatedRefund:
    cf_refund_id: str
    status: str
    raw: dict


@dataclass(frozen=True, slots=True)
class FetchedOrder:
    merchant_order_id: str
    order_status: str
    cf_payment_id: str | None
    raw: dict


class PaymentProvider(Protocol):
    async def create_order(
        self,
        *,
        merchant_order_id: str,
        amount: Decimal,
        currency: str,
        customer_id: str,
        customer_email: str,
        customer_phone: str,
        customer_name: str,
        return_url: str,
        notify_url: str | None,
        payment_methods: str | None,
        idempotency_key: str,
    ) -> CreatedOrder: ...

    async def create_refund(
        self,
        *,
        merchant_order_id: str,
        refund_id: str,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
    ) -> CreatedRefund: ...

    async def fetch_order(self, *, merchant_order_id: str) -> FetchedOrder: ...


class StubPaymentProvider:
    """Offline provider for tests and local docker without Cashfree credentials."""

    async def create_order(
        self,
        *,
        merchant_order_id: str,
        amount: Decimal,
        currency: str,
        customer_id: str,
        customer_email: str,
        customer_phone: str,
        customer_name: str,
        return_url: str,
        notify_url: str | None,
        payment_methods: str | None,
        idempotency_key: str,
    ) -> CreatedOrder:
        session = f"stub_session_{merchant_order_id}"
        return CreatedOrder(
            merchant_order_id=merchant_order_id,
            cf_order_id=f"stub_cf_{merchant_order_id[:20]}",
            payment_session_id=session,
            order_status="ACTIVE",
            raw={
                "order_id": merchant_order_id,
                "cf_order_id": f"stub_cf_{merchant_order_id[:20]}",
                "payment_session_id": session,
                "order_amount": float(amount),
                "order_currency": currency,
                "order_status": "ACTIVE",
                "customer_details": {
                    "customer_id": customer_id,
                    "customer_email": customer_email,
                    "customer_phone": customer_phone,
                    "customer_name": customer_name,
                },
                "order_meta": {
                    "return_url": return_url,
                    "notify_url": notify_url,
                    "payment_methods": payment_methods,
                },
                "idempotency_key": idempotency_key,
            },
        )

    async def create_refund(
        self,
        *,
        merchant_order_id: str,
        refund_id: str,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
    ) -> CreatedRefund:
        cf_id = f"stub_refund_{refund_id[:16]}"
        return CreatedRefund(
            cf_refund_id=cf_id,
            status="SUCCESS",
            raw={
                "cf_refund_id": cf_id,
                "refund_id": refund_id,
                "order_id": merchant_order_id,
                "refund_amount": float(amount),
                "refund_status": "SUCCESS",
                "refund_note": reason,
                "idempotency_key": idempotency_key,
            },
        )

    async def fetch_order(self, *, merchant_order_id: str) -> FetchedOrder:
        return FetchedOrder(
            merchant_order_id=merchant_order_id,
            order_status="ACTIVE",
            cf_payment_id=None,
            raw={"order_id": merchant_order_id, "order_status": "ACTIVE"},
        )


class CashfreeClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        app_id: str | None = None,
        secret_key: str | None = None,
        api_version: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = (base_url or settings.cashfree_base_url).rstrip("/")
        self._app_id = app_id if app_id is not None else settings.cashfree_app_id
        self._secret_key = (
            secret_key if secret_key is not None else settings.cashfree_secret_key
        )
        self._api_version = api_version or settings.cashfree_api_version
        self._timeout = timeout
        if not self._app_id or not self._secret_key:
            raise ValidationError("Cashfree credentials are not configured")

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "x-client-id": self._app_id,
            "x-client-secret": self._secret_key,
            "x-api-version": self._api_version,
            "x-request-id": str(uuid.uuid4()),
        }
        if idempotency_key:
            headers["x-idempotency-key"] = idempotency_key
        return headers

    async def create_order(
        self,
        *,
        merchant_order_id: str,
        amount: Decimal,
        currency: str,
        customer_id: str,
        customer_email: str,
        customer_phone: str,
        customer_name: str,
        return_url: str,
        notify_url: str | None,
        payment_methods: str | None,
        idempotency_key: str,
    ) -> CreatedOrder:
        body: dict[str, Any] = {
            "order_id": merchant_order_id,
            "order_amount": float(amount),
            "order_currency": currency,
            "customer_details": {
                "customer_id": customer_id[:50],
                "customer_email": customer_email,
                "customer_phone": customer_phone,
                "customer_name": customer_name or "Customer",
            },
            "order_meta": {
                "return_url": return_url,
            },
        }
        if notify_url:
            body["order_meta"]["notify_url"] = notify_url
        if payment_methods:
            body["order_meta"]["payment_methods"] = payment_methods

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/orders",
                headers=self._headers(idempotency_key=idempotency_key),
                json=body,
            )
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json()
            except Exception:
                pass
            raise ValidationError(f"Cashfree create order failed: {detail}")
        data = response.json()
        return CreatedOrder(
            merchant_order_id=str(data.get("order_id") or merchant_order_id),
            cf_order_id=str(data.get("cf_order_id") or ""),
            payment_session_id=str(data.get("payment_session_id") or ""),
            order_status=str(data.get("order_status") or "ACTIVE"),
            raw=data if isinstance(data, dict) else {"response": data},
        )

    async def create_refund(
        self,
        *,
        merchant_order_id: str,
        refund_id: str,
        amount: Decimal,
        reason: str,
        idempotency_key: str,
    ) -> CreatedRefund:
        body = {
            "refund_amount": float(amount),
            "refund_id": refund_id,
            "refund_note": reason[:200] or "refund",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/orders/{merchant_order_id}/refunds",
                headers=self._headers(idempotency_key=idempotency_key),
                json=body,
            )
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json()
            except Exception:
                pass
            raise ValidationError(f"Cashfree refund failed: {detail}")
        data = response.json()
        status = str(
            data.get("refund_status") or data.get("status") or "PENDING"
        ).upper()
        return CreatedRefund(
            cf_refund_id=str(data.get("cf_refund_id") or data.get("refund_id") or refund_id),
            status=status,
            raw=data if isinstance(data, dict) else {"response": data},
        )

    async def fetch_order(self, *, merchant_order_id: str) -> FetchedOrder:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/orders/{merchant_order_id}",
                headers=self._headers(),
            )
            payments_response = None
            if response.status_code < 400:
                payments_response = await client.get(
                    f"{self._base_url}/orders/{merchant_order_id}/payments",
                    headers=self._headers(),
                )
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json()
            except Exception:
                pass
            raise ValidationError(f"Cashfree fetch order failed: {detail}")
        data = response.json()
        payments = data.get("payments") if isinstance(data, dict) else None
        if not isinstance(payments, list) and payments_response is not None:
            if payments_response.status_code < 400:
                try:
                    body = payments_response.json()
                except Exception:
                    body = None
                if isinstance(body, list):
                    payments = body
                elif isinstance(body, dict) and isinstance(body.get("payments"), list):
                    payments = body["payments"]
        cf_payment_id = None
        payment_success = False
        if isinstance(payments, list):
            for item in payments:
                if not isinstance(item, dict):
                    continue
                pay_status = str(
                    item.get("payment_status") or item.get("status") or ""
                ).upper()
                if pay_status in {"SUCCESS", "PAID"}:
                    payment_success = True
                    cf_payment_id = str(item.get("cf_payment_id") or "") or None
                    break
            if not cf_payment_id and payments:
                first = payments[0]
                if isinstance(first, dict):
                    cf_payment_id = str(first.get("cf_payment_id") or "") or None
        if not cf_payment_id and isinstance(data, dict):
            cf_payment_id = str(data.get("cf_payment_id") or "") or None
        order_status = str(data.get("order_status") or "")
        if payment_success and order_status.upper() not in {"PAID", "SUCCESS"}:
            order_status = "PAID"
        if isinstance(data, dict):
            data = {**data, "payments": payments or data.get("payments")}
        return FetchedOrder(
            merchant_order_id=str(data.get("order_id") or merchant_order_id),
            order_status=order_status,
            cf_payment_id=cf_payment_id,
            raw=data if isinstance(data, dict) else {"response": data},
        )


def get_payment_provider() -> PaymentProvider:
    if settings.payments_provider_normalized == "cashfree":
        return CashfreeClient()
    return StubPaymentProvider()
