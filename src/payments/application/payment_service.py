"""Checkout sessions, Cashfree webhooks, and refunds."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from identity.domain.security import utcnow
from identity.infrastructure.models import UserRow
from marketplace.application.access import audit
from marketplace.application.commerce_service import PAYMENT_METHODS
from marketplace.domain.fulfilment import ADDRESS_REQUIRED
from marketplace.infrastructure.models import (
    CartLineRow,
    CartRow,
    OfferingRow,
    OrderLineRow,
    OrderRow,
    ProductRow,
    VendorFulfilmentRow,
)
from payments.application.cashfree_client import PaymentProvider, get_payment_provider
from payments.application.webhook_verify import verify_cashfree_signature
from payments.infrastructure.models import PaymentEventRow, PaymentIntentRow, PaymentRefundRow
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from shared.settings import settings
from tenant.infrastructure.models import AddressRow, TenantMembershipRow, TenantRow

METHOD_TO_CF = {
    "upi": "upi",
    "card": "cc,dc",
    "netbanking": "nb",
}


@dataclass(frozen=True, slots=True)
class CheckoutSessionView:
    order_id: str
    payment_intent_id: str
    payment_session_id: str
    merchant_order_id: str
    amount: float
    currency: str
    status: str
    cf_env: str
    provider: str
    cashfree_app_id: str
    return_url: str


@dataclass(frozen=True, slots=True)
class PaymentStatusView:
    order_id: str
    order_status: str
    payment_status: str
    payment_session_id: str | None
    amount: float
    currency: str
    provider: str
    cf_payment_id: str | None
    provider_order_status: str | None = None
    reconcile_note: str | None = None


@dataclass(frozen=True, slots=True)
class RefundView:
    id: str
    order_id: str
    amount: float
    status: str
    cf_refund_id: str | None


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        authorization: AuthorizationService | None = None,
        provider: PaymentProvider | None = None,
    ) -> None:
        self._session = session
        self._authorization = authorization
        self._provider = provider or get_payment_provider()

    async def create_checkout_session(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        caller_principal_id: UUID,
        address_id: UUID | None,
        payment_method: str = "upi",
        request_id: str | None = None,
        notify_base_url: str | None = None,
    ) -> CheckoutSessionView:
        await self._require_permission(
            caller_principal_id, tenant_id, "resource.create", request_id
        )
        method = payment_method.strip().lower() or "upi"
        if method not in PAYMENT_METHODS:
            raise ValidationError("payment_method must be upi, card, or netbanking")

        cart = await self._open_or_pending_cart(tenant_id)
        if cart is None:
            raise ConflictError("cart empty")
        lines = await self._cart_line_rows(cart.id)
        if not lines:
            raise ConflictError("cart empty")

        needs_address = any(
            product.fulfilment_type in ADDRESS_REQUIRED for _line, _offering, product in lines
        )
        address: AddressRow | None = None
        if needs_address:
            if address_id is None:
                raise ValidationError("address_id is required for this cart")
            address = await self._address(tenant_id, address_id)
        elif address_id is not None:
            address = await self._address(tenant_id, address_id)

        user = await self._session.get(UserRow, caller_user_id)
        if user is None:
            raise NotFoundError("user not found")
        phone = (address.phone if address else "") or ""
        phone = re.sub(r"\D", "", phone)
        if len(phone) < 10:
            raise ValidationError(
                "a valid phone number is required for payment (set it on the delivery address)"
            )
        if len(phone) > 10 and phone.startswith("91"):
            phone = phone[-10:]

        amount = sum(
            (Decimal(str(offering.price_usd)) * line.quantity)
            for line, offering, _product in lines
        )
        if amount <= 0:
            raise ValidationError("order amount must be greater than zero")

        existing = (
            await self._session.execute(
                select(OrderRow)
                .where(
                    OrderRow.tenant_id == tenant_id,
                    OrderRow.cart_id == cart.id,
                    OrderRow.status == "awaiting_payment",
                )
                .order_by(OrderRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            intent = (
                await self._session.execute(
                    select(PaymentIntentRow).where(PaymentIntentRow.order_id == existing.id)
                )
            ).scalar_one_or_none()
            if intent is not None and intent.status in {"created", "active"}:
                return self._session_view(existing, intent)

        order = OrderRow(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            cart_id=cart.id,
            address_id=address.id if address else None,
            payment_method=method,
            status="awaiting_payment",
        )
        self._session.add(order)
        await self._session.flush()

        vendor_ids: set[UUID] = set()
        for line, offering, product in lines:
            self._session.add(
                OrderLineRow(
                    id=uuid.uuid4(),
                    order_id=order.id,
                    offering_id=offering.id,
                    product_name=product.name,
                    plan_name=offering.plan_name,
                    quantity=line.quantity,
                    fulfilment_type=product.fulfilment_type,
                    billing_period=offering.billing_period,
                    unit_price=offering.price_usd,
                    currency=getattr(offering, "currency", None) or "INR",
                    status="pending",
                )
            )
            vendor_ids.add(product.vendor_id)
        for vendor_id in vendor_ids:
            self._session.add(
                VendorFulfilmentRow(
                    id=uuid.uuid4(),
                    order_id=order.id,
                    vendor_id=vendor_id,
                    status="awaiting_payment",
                    refund_status="none",
                )
            )

        cart.status = "pending_payment"
        merchant_order_id = f"ap_{order.id.hex[:24]}"
        return_base = settings.cashfree_return_url_base.rstrip("/")
        if "://" in return_base and not return_base.startswith(("http://", "https://")):
            sep = "&" if "?" in return_base else "?"
            return_url = f"{return_base}{sep}payment=return&order_id={order.id}"
        else:
            return_url = (
                f"{return_base}/app/marketplace/orders"
                f"?payment=return&order_id={order.id}"
            )
        notify_url = None
        if notify_base_url:
            notify_url = f"{notify_base_url.rstrip('/')}/api/v1/webhooks/cashfree/payments"

        created = await self._provider.create_order(
            merchant_order_id=merchant_order_id,
            amount=amount,
            currency="INR",
            customer_id=str(caller_user_id),
            customer_email=user.email,
            customer_phone=phone,
            customer_name=(
                user.display_name
                or (address.contact_name if address else "")
                or user.email
            ),
            return_url=return_url,
            notify_url=notify_url,
            # Omit method filter so sandbox/mobile checkout can show all instruments.
            # Preferred method is still stored on the order for analytics.
            payment_methods=None,
            idempotency_key=str(order.id),
        )

        provider_name = settings.payments_provider_normalized
        intent = PaymentIntentRow(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            order_id=order.id,
            provider=provider_name if provider_name == "stub" else "cashfree",
            merchant_order_id=created.merchant_order_id,
            cf_order_id=created.cf_order_id or None,
            payment_session_id=created.payment_session_id,
            amount=amount,
            currency="INR",
            status="active",
            payment_method=method,
            meta={"create_response": created.raw, "return_url": return_url},
        )
        self._session.add(intent)
        await audit(
            self._session,
            action="payment.session_created",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={
                "order_id": str(order.id),
                "payment_intent_id": str(intent.id),
                "amount": float(amount),
                "provider": intent.provider,
            },
        )
        await self._session.commit()
        await self._session.refresh(order)
        await self._session.refresh(intent)
        return self._session_view(order, intent)

    async def get_payment_status(
        self, *, tenant_id: UUID, order_id: UUID, caller_user_id: UUID
    ) -> PaymentStatusView:
        await self._require_member(tenant_id, caller_user_id)
        order = await self._session.get(OrderRow, order_id)
        if order is None or order.tenant_id != tenant_id:
            raise NotFoundError("order not found")
        intent = (
            await self._session.execute(
                select(PaymentIntentRow).where(PaymentIntentRow.order_id == order_id)
            )
        ).scalar_one_or_none()
        if intent is None:
            return PaymentStatusView(
                order_id=str(order.id),
                order_status=order.status,
                payment_status="none",
                payment_session_id=None,
                amount=0.0,
                currency="INR",
                provider="none",
                cf_payment_id=None,
            )
        note = None
        provider_status = None
        if intent.status in {"created", "active"} and order.status == "awaiting_payment":
            note, provider_status = await self._reconcile_intent(
                intent, actor_user_id=caller_user_id
            )
            await self._session.refresh(order)
            await self._session.refresh(intent)
        return PaymentStatusView(
            order_id=str(order.id),
            order_status=order.status,
            payment_status=intent.status,
            payment_session_id=intent.payment_session_id,
            amount=float(intent.amount or 0),
            currency=intent.currency,
            provider=intent.provider,
            cf_payment_id=intent.cf_payment_id,
            provider_order_status=provider_status,
            reconcile_note=note,
        )

    async def reconcile_payment(
        self, *, tenant_id: UUID, order_id: UUID, caller_user_id: UUID
    ) -> PaymentStatusView:
        """Pull latest status from Cashfree and capture if paid (covers missed webhooks)."""
        await self._require_member(tenant_id, caller_user_id)
        intent = await self._intent_for_order(tenant_id, order_id)
        note = None
        provider_status = None
        if intent.status != "paid":
            note, provider_status = await self._reconcile_intent(
                intent, actor_user_id=caller_user_id
            )
        view = await self.get_payment_status(
            tenant_id=tenant_id, order_id=order_id, caller_user_id=caller_user_id
        )
        if note or provider_status:
            return PaymentStatusView(
                order_id=view.order_id,
                order_status=view.order_status,
                payment_status=view.payment_status,
                payment_session_id=view.payment_session_id,
                amount=view.amount,
                currency=view.currency,
                provider=view.provider,
                cf_payment_id=view.cf_payment_id,
                provider_order_status=provider_status or view.provider_order_status,
                reconcile_note=note or view.reconcile_note,
            )
        return view

    async def _reconcile_intent(
        self, intent: PaymentIntentRow, *, actor_user_id: UUID | None
    ) -> tuple[str | None, str | None]:
        if intent.status == "paid":
            return ("already paid", "PAID")
        try:
            fetched = await self._provider.fetch_order(
                merchant_order_id=intent.merchant_order_id
            )
        except ValidationError as exc:
            return (f"Cashfree fetch failed: {exc}", None)
        status = (fetched.order_status or "").upper()
        if status in {"PAID", "SUCCESS"}:
            await self._capture_payment(
                intent,
                cf_payment_id=fetched.cf_payment_id,
                actor_user_id=actor_user_id,
                event_type="RECONCILE_FETCH_ORDER",
                payload=fetched.raw,
            )
            await self._session.commit()
            return ("captured from Cashfree", status)
        if status in {"EXPIRED", "TERMINATED", "CANCELLED"}:
            await self._fail_payment(intent, status="expired", event_type="RECONCILE_FETCH_ORDER")
            await self._session.commit()
            return (f"payment {status.lower()} at Cashfree", status)
        return (
            "Cashfree still unpaid — complete checkout, then reconcile again",
            status or "UNKNOWN",
        )

    async def simulate_pay(
        self, *, tenant_id: UUID, order_id: UUID, caller_user_id: UUID
    ) -> PaymentStatusView:
        """Dev/stub helper — marks payment captured without Cashfree."""
        if settings.payments_provider_normalized != "stub" and settings.app_env not in {
            "dev",
            "test",
        }:
            raise ForbiddenError("simulate pay is only available in stub/dev")
        await self._require_member(tenant_id, caller_user_id)
        intent = await self._intent_for_order(tenant_id, order_id)
        if intent.status == "paid":
            return await self.get_payment_status(
                tenant_id=tenant_id, order_id=order_id, caller_user_id=caller_user_id
            )
        await self._capture_payment(
            intent,
            cf_payment_id=f"stub_pay_{intent.merchant_order_id[:16]}",
            actor_user_id=caller_user_id,
            event_type="SIMULATE_PAY",
            payload={"source": "simulate_pay"},
        )
        await self._session.commit()
        return await self.get_payment_status(
            tenant_id=tenant_id, order_id=order_id, caller_user_id=caller_user_id
        )

    async def handle_cashfree_webhook(
        self,
        *,
        raw_body: bytes,
        timestamp: str | None,
        signature: str | None,
        idempotency_key: str | None,
    ) -> dict:
        body_text = raw_body.decode("utf-8") if raw_body else "{}"
        try:
            payload = json.loads(body_text) if body_text else {}
        except json.JSONDecodeError as exc:
            raise ValidationError("invalid webhook JSON") from exc

        secret = settings.cashfree_webhook_secret or settings.cashfree_secret_key
        signature_ok = False
        if signature and timestamp and secret:
            signature_ok = verify_cashfree_signature(
                raw_body=body_text,
                timestamp=timestamp,
                signature=signature,
                secret=secret,
            )
        elif settings.app_env in {"dev", "test"} and settings.payments_provider_normalized == "stub":
            signature_ok = True
        elif settings.app_env not in {"dev", "test"}:
            raise ForbiddenError("invalid webhook signature")

        if not signature_ok and settings.app_env not in {"dev", "test"}:
            raise ForbiddenError("invalid webhook signature")

        event_type = str(
            payload.get("type")
            or payload.get("event")
            or ((payload.get("data") or {}) if isinstance(payload.get("data"), dict) else {}).get(
                "type"
            )
            or "UNKNOWN"
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        order_obj = data.get("order") if isinstance(data.get("order"), dict) else {}
        payment_obj = data.get("payment") if isinstance(data.get("payment"), dict) else {}
        merchant_order_id = str(
            order_obj.get("order_id")
            or data.get("order_id")
            or payload.get("order_id")
            or ""
        )
        cf_payment_id = str(
            payment_obj.get("cf_payment_id")
            or data.get("cf_payment_id")
            or ""
        ) or None

        intent: PaymentIntentRow | None = None
        if merchant_order_id:
            intent = (
                await self._session.execute(
                    select(PaymentIntentRow).where(
                        PaymentIntentRow.merchant_order_id == merchant_order_id
                    )
                )
            ).scalar_one_or_none()

        if idempotency_key:
            existing_event = (
                await self._session.execute(
                    select(PaymentEventRow).where(
                        PaymentEventRow.provider == "cashfree",
                        PaymentEventRow.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing_event is not None:
                return {"status": "duplicate", "event_type": event_type}

        event = PaymentEventRow(
            id=uuid.uuid4(),
            payment_intent_id=intent.id if intent else None,
            provider="cashfree",
            event_type=event_type,
            idempotency_key=idempotency_key,
            signature_ok=signature_ok,
            payload=payload if isinstance(payload, dict) else {"raw": body_text},
        )
        self._session.add(event)

        if intent is None:
            await self._session.commit()
            return {"status": "ignored", "reason": "unknown_order", "event_type": event_type}

        upper = event_type.upper()
        if "SUCCESS" in upper or upper.endswith("PAID") or upper == "PAYMENT_SUCCESS_WEBHOOK":
            await self._capture_payment(
                intent,
                cf_payment_id=cf_payment_id,
                actor_user_id=None,
                event_type=event_type,
                payload=payload if isinstance(payload, dict) else {},
            )
        elif "FAILED" in upper:
            await self._fail_payment(intent, status="failed", event_type=event_type)
        elif "USER_DROPPED" in upper or "DROPPED" in upper:
            await self._fail_payment(intent, status="user_dropped", event_type=event_type)

        await self._session.commit()
        return {
            "status": "ok",
            "event_type": event_type,
            "payment_status": intent.status,
            "order_id": str(intent.order_id),
        }

    async def create_refund(
        self,
        *,
        order_id: UUID,
        amount: Decimal,
        reason: str = "",
        return_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        refund_method: str = "original",
    ) -> RefundView:
        intent = (
            await self._session.execute(
                select(PaymentIntentRow).where(PaymentIntentRow.order_id == order_id)
            )
        ).scalar_one_or_none()
        if intent is None:
            raise NotFoundError("payment intent not found for order")
        if intent.status != "paid":
            raise ConflictError("order payment is not captured")
        if amount <= 0:
            raise ValidationError("refund amount must be greater than zero")
        if amount > intent.amount:
            raise ValidationError("refund amount exceeds paid amount")

        method = (refund_method or "original").strip().lower()
        refund_row = PaymentRefundRow(
            id=uuid.uuid4(),
            payment_intent_id=intent.id,
            order_id=order_id,
            return_id=return_id,
            amount=amount,
            currency=intent.currency,
            status="pending",
            reason=(reason or "")[:255],
            meta={"refund_method": method},
        )
        self._session.add(refund_row)
        await self._session.flush()

        if method != "original" and settings.payments_provider_normalized == "cashfree":
            # Non-original methods stay ledger-only for now.
            refund_row.status = "recorded"
            refund_row.updated_at = utcnow()
        else:
            created = await self._provider.create_refund(
                merchant_order_id=intent.merchant_order_id,
                refund_id=f"rf_{refund_row.id.hex[:20]}",
                amount=amount,
                reason=reason or "refund",
                idempotency_key=str(refund_row.id),
            )
            refund_row.cf_refund_id = created.cf_refund_id
            refund_row.status = (
                "success"
                if created.status in {"SUCCESS", "PENDING", "ONHOLD", "success", "pending"}
                else created.status.lower()
            )
            if created.status.upper() == "SUCCESS":
                refund_row.status = "success"
            elif created.status.upper() in {"PENDING", "ONHOLD"}:
                refund_row.status = "pending"
            refund_row.meta = {**dict(refund_row.meta or {}), "create_response": created.raw}
            refund_row.updated_at = utcnow()

        await audit(
            self._session,
            action="payment.refund_initiated",
            actor_user_id=actor_user_id,
            tenant_id=intent.tenant_id,
            payload={
                "order_id": str(order_id),
                "refund_id": str(refund_row.id),
                "amount": float(amount),
                "status": refund_row.status,
                "cf_refund_id": refund_row.cf_refund_id,
            },
        )
        await self._session.commit()
        await self._session.refresh(refund_row)
        return RefundView(
            id=str(refund_row.id),
            order_id=str(order_id),
            amount=float(refund_row.amount),
            status=refund_row.status,
            cf_refund_id=refund_row.cf_refund_id,
        )

    async def _capture_payment(
        self,
        intent: PaymentIntentRow,
        *,
        cf_payment_id: str | None,
        actor_user_id: UUID | None,
        event_type: str,
        payload: dict,
    ) -> None:
        if intent.status == "paid":
            return
        order = await self._session.get(OrderRow, intent.order_id)
        if order is None:
            raise NotFoundError("order not found")
        intent.status = "paid"
        intent.cf_payment_id = cf_payment_id or intent.cf_payment_id
        intent.updated_at = utcnow()
        intent.meta = {
            **dict(intent.meta or {}),
            "capture_event": event_type,
            "capture_payload": payload,
        }
        order.status = "placed"
        cart = await self._session.get(CartRow, order.cart_id)
        if cart is not None and cart.status in {"open", "pending_payment"}:
            cart.status = "checked_out"
        lines = (
            await self._session.execute(
                select(OrderLineRow).where(OrderLineRow.order_id == order.id)
            )
        ).scalars().all()
        for line in lines:
            if line.status == "pending":
                line.status = "active"
        fulfilments = (
            await self._session.execute(
                select(VendorFulfilmentRow).where(VendorFulfilmentRow.order_id == order.id)
            )
        ).scalars().all()
        for fulfilment in fulfilments:
            if fulfilment.status == "awaiting_payment":
                fulfilment.status = "placed"
                fulfilment.updated_at = utcnow()
        await audit(
            self._session,
            action="payment.captured",
            actor_user_id=actor_user_id,
            tenant_id=intent.tenant_id,
            payload={
                "order_id": str(order.id),
                "payment_intent_id": str(intent.id),
                "cf_payment_id": intent.cf_payment_id,
                "event_type": event_type,
            },
        )

    async def _fail_payment(
        self, intent: PaymentIntentRow, *, status: str, event_type: str
    ) -> None:
        if intent.status == "paid":
            return
        intent.status = status
        intent.updated_at = utcnow()
        order = await self._session.get(OrderRow, intent.order_id)
        if order is not None and order.status == "awaiting_payment":
            order.status = "payment_failed" if status == "failed" else "payment_dropped"
        cart = await self._session.get(CartRow, order.cart_id) if order else None
        if cart is not None and cart.status == "pending_payment":
            # Allow retry — reopen cart.
            cart.status = "open"
        await audit(
            self._session,
            action="payment.failed",
            actor_user_id=None,
            tenant_id=intent.tenant_id,
            payload={
                "order_id": str(intent.order_id),
                "payment_intent_id": str(intent.id),
                "status": status,
                "event_type": event_type,
            },
        )

    def _session_view(self, order: OrderRow, intent: PaymentIntentRow) -> CheckoutSessionView:
        return CheckoutSessionView(
            order_id=str(order.id),
            payment_intent_id=str(intent.id),
            payment_session_id=intent.payment_session_id or "",
            merchant_order_id=intent.merchant_order_id,
            amount=float(intent.amount or 0),
            currency=intent.currency,
            status=intent.status,
            cf_env=settings.cashfree_env,
            provider=intent.provider,
            cashfree_app_id=settings.cashfree_app_id if intent.provider == "cashfree" else "",
            return_url=str((intent.meta or {}).get("return_url") or ""),
        )

    async def _intent_for_order(self, tenant_id: UUID, order_id: UUID) -> PaymentIntentRow:
        order = await self._session.get(OrderRow, order_id)
        if order is None or order.tenant_id != tenant_id:
            raise NotFoundError("order not found")
        intent = (
            await self._session.execute(
                select(PaymentIntentRow).where(PaymentIntentRow.order_id == order_id)
            )
        ).scalar_one_or_none()
        if intent is None:
            raise NotFoundError("payment intent not found")
        return intent

    async def _require_permission(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        permission: str,
        request_id: str | None,
    ) -> None:
        if self._authorization is None:
            raise ForbiddenError("authorization service required")
        decision = await self._authorization.authorize(
            AuthorizeCommand(
                principal_id=principal_id,
                permission_code=permission,
                api_surface=ApiSurface.PUBLIC,
                tenant_id=tenant_id,
                request_id=request_id,
            )
        )
        if not decision.allowed:
            raise ForbiddenError(public_forbid_detail(decision.reason))

    async def _require_member(self, tenant_id: UUID, user_id: UUID) -> None:
        tenant = await self._session.get(TenantRow, tenant_id)
        if tenant is None:
            raise NotFoundError("tenant not found")
        membership = (
            await self._session.execute(
                select(TenantMembershipRow.id).where(
                    TenantMembershipRow.tenant_id == tenant_id,
                    TenantMembershipRow.user_id == user_id,
                    TenantMembershipRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            raise ForbiddenError("not a member of the tenant")

    async def _open_or_pending_cart(self, tenant_id: UUID) -> CartRow | None:
        return (
            await self._session.execute(
                select(CartRow)
                .where(
                    CartRow.tenant_id == tenant_id,
                    CartRow.status.in_(("open", "pending_payment")),
                )
                .order_by(CartRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _cart_line_rows(
        self, cart_id: UUID
    ) -> list[tuple[CartLineRow, OfferingRow, ProductRow]]:
        rows = (
            await self._session.execute(
                select(CartLineRow, OfferingRow, ProductRow)
                .join(OfferingRow, OfferingRow.id == CartLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(CartLineRow.cart_id == cart_id)
            )
        ).all()
        return [(r[0], r[1], r[2]) for r in rows]

    async def _address(self, tenant_id: UUID, address_id: UUID) -> AddressRow:
        row = await self._session.get(AddressRow, address_id)
        if row is None or row.tenant_id != tenant_id:
            raise NotFoundError("address not found")
        return row
