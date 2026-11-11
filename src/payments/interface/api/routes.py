from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.interface.api.dependencies import get_authorization_service
from identity.interface.api.dependencies import CurrentAuthDep, get_session
from payments.application.payment_service import PaymentService
from shared.settings import settings

router = APIRouter(prefix="/api/v1", tags=["payments"])


class CheckoutSessionRequest(BaseModel):
    address_id: str | None = None
    payment_method: str = Field(default="upi")


class CheckoutSessionResponse(BaseModel):
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


class PaymentStatusResponse(BaseModel):
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


def get_payment_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> PaymentService:
    return PaymentService(session, authorization)


@router.post(
    "/tenants/{tenant_id}/checkout/sessions",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout_session(
    tenant_id: UUID,
    body: CheckoutSessionRequest,
    auth: CurrentAuthDep,
    service: Annotated[PaymentService, Depends(get_payment_service)],
    request: Request,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> CheckoutSessionResponse:
    user, _session, _credential = auth
    notify_base = str(request.base_url).rstrip("/")
    view = await service.create_checkout_session(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        caller_principal_id=user.principal_id,
        address_id=UUID(body.address_id) if body.address_id else None,
        payment_method=body.payment_method,
        request_id=x_request_id,
        notify_base_url=notify_base,
    )
    return CheckoutSessionResponse(**asdict_safe(view))


@router.get(
    "/tenants/{tenant_id}/orders/{order_id}/payment",
    response_model=PaymentStatusResponse,
)
async def get_order_payment(
    tenant_id: UUID,
    order_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> PaymentStatusResponse:
    user, _session, _credential = auth
    view = await service.get_payment_status(
        tenant_id=tenant_id, order_id=order_id, caller_user_id=user.id
    )
    return PaymentStatusResponse(**asdict_safe(view))


@router.post(
    "/tenants/{tenant_id}/orders/{order_id}/payment/simulate",
    response_model=PaymentStatusResponse,
)
async def simulate_order_payment(
    tenant_id: UUID,
    order_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> PaymentStatusResponse:
    user, _session, _credential = auth
    view = await service.simulate_pay(
        tenant_id=tenant_id, order_id=order_id, caller_user_id=user.id
    )
    return PaymentStatusResponse(**asdict_safe(view))


@router.post(
    "/tenants/{tenant_id}/orders/{order_id}/payment/reconcile",
    response_model=PaymentStatusResponse,
)
async def reconcile_order_payment(
    tenant_id: UUID,
    order_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[PaymentService, Depends(get_payment_service)],
) -> PaymentStatusResponse:
    user, _session, _credential = auth
    view = await service.reconcile_payment(
        tenant_id=tenant_id, order_id=order_id, caller_user_id=user.id
    )
    return PaymentStatusResponse(**asdict_safe(view))


@router.post("/webhooks/cashfree/payments")
async def cashfree_payment_webhook(
    request: Request,
    service: Annotated[PaymentService, Depends(get_payment_service)],
    x_webhook_signature: Annotated[str | None, Header(alias="x-webhook-signature")] = None,
    x_webhook_timestamp: Annotated[str | None, Header(alias="x-webhook-timestamp")] = None,
    x_idempotency_header: Annotated[str | None, Header(alias="x-idempotency-header")] = None,
) -> dict:
    raw = await request.body()
    return await service.handle_cashfree_webhook(
        raw_body=raw,
        timestamp=x_webhook_timestamp,
        signature=x_webhook_signature,
        idempotency_key=x_idempotency_header,
    )


@router.get("/payments/config")
async def payments_public_config() -> dict:
    """Non-secret client config for checkout JS."""
    return {
        "provider": settings.payments_provider_normalized,
        "cf_env": settings.cashfree_env,
        "cashfree_app_id": (
            settings.cashfree_app_id
            if settings.payments_provider_normalized == "cashfree"
            else ""
        ),
    }


def asdict_safe(view) -> dict:
    from dataclasses import asdict

    return asdict(view)
