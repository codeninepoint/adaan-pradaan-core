from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.interface.api.dependencies import get_authorization_service
from identity.interface.api.dependencies import CurrentAuthDep, get_session
from marketplace.application.commerce_service import CommerceService

router = APIRouter(prefix="/api/v1", tags=["marketplace-commerce"])


class WishlistItemResponse(BaseModel):
    product_id: str
    name: str
    vendor_name: str
    fulfilment_type: str


class WishlistResponse(BaseModel):
    items: list[WishlistItemResponse]


class WishlistAddRequest(BaseModel):
    product_id: str


class CartLineResponse(BaseModel):
    line_id: str
    offering_id: str
    product_id: str
    product_name: str
    plan_name: str
    quantity: int
    unit_price: float
    fulfilment_type: str
    billing_period: str


class CartResponse(BaseModel):
    cart_id: str | None
    status: str
    lines: list[CartLineResponse]


class AddCartLineRequest(BaseModel):
    offering_id: str
    quantity: int = 1


class UpdateCartLineRequest(BaseModel):
    quantity: int


class AddressResponse(BaseModel):
    address_id: str
    label: str
    contact_name: str
    line1: str
    city: str
    state: str
    pincode: str
    phone: str


class AddressListResponse(BaseModel):
    addresses: list[AddressResponse]


class AddressRequest(BaseModel):
    label: str
    contact_name: str
    line1: str
    city: str
    state: str
    pincode: str
    phone: str


class AddressPatchRequest(BaseModel):
    label: str | None = None
    contact_name: str | None = None
    line1: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    phone: str | None = None


class PlaceOrderRequest(BaseModel):
    address_id: str | None = None
    payment_method: str


class PlaceOrderResponse(BaseModel):
    order_id: str
    status: str
    line_count: int


class OrderSummaryResponse(BaseModel):
    order_id: str
    status: str
    payment_method: str
    placed_at: str
    line_count: int
    total: float


class OrderListResponse(BaseModel):
    orders: list[OrderSummaryResponse]


class OrderLineResponse(BaseModel):
    line_id: str
    offering_id: str
    product_name: str
    plan_name: str
    quantity: int
    fulfilment_type: str
    billing_period: str
    unit_price: float
    status: str


class OrderDetailResponse(BaseModel):
    order_id: str
    status: str
    payment_method: str
    address_id: str | None
    placed_at: str
    tracking: None = None
    lines: list[OrderLineResponse]


class ReturnRequest(BaseModel):
    line_id: str
    reason: str
    notes: str = ""


class ReturnResponse(BaseModel):
    return_id: str
    order_id: str
    line_id: str
    product_name: str
    reason: str
    status: str


class ReturnListResponse(BaseModel):
    returns: list[ReturnResponse]


class SubscriptionResponse(BaseModel):
    offering_id: str
    product_name: str
    plan_name: str
    status: str
    next_billing_at: str | None


class SubscriptionListResponse(BaseModel):
    subscriptions: list[SubscriptionResponse]
    active_count: int = Field(default=0)


def get_commerce_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[AuthorizationService, Depends(get_authorization_service)],
) -> CommerceService:
    return CommerceService(session, authorization)


def _cart(view) -> CartResponse:
    return CartResponse(
        cart_id=str(view.cart_id) if view.cart_id else None,
        status=view.status,
        lines=[
            CartLineResponse(
                line_id=str(line.line_id),
                offering_id=str(line.offering_id),
                product_id=str(line.product_id),
                product_name=line.product_name,
                plan_name=line.plan_name,
                quantity=line.quantity,
                unit_price=line.unit_price,
                fulfilment_type=line.fulfilment_type,
                billing_period=line.billing_period,
            )
            for line in view.lines
        ],
    )


def _address(item) -> AddressResponse:
    return AddressResponse(
        address_id=str(item.address_id),
        label=item.label,
        contact_name=item.contact_name,
        line1=item.line1,
        city=item.city,
        state=item.state,
        pincode=item.pincode,
        phone=item.phone,
    )


@router.get("/tenants/{tenant_id}/wishlist", response_model=WishlistResponse)
async def list_wishlist(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> WishlistResponse:
    user, _session, _credential = auth
    items = await service.list_wishlist(tenant_id=tenant_id, caller_user_id=user.id)
    return WishlistResponse(
        items=[
            WishlistItemResponse(
                product_id=str(item.product_id),
                name=item.name,
                vendor_name=item.vendor_name,
                fulfilment_type=item.fulfilment_type,
            )
            for item in items
        ]
    )


@router.post(
    "/tenants/{tenant_id}/wishlist",
    status_code=status.HTTP_201_CREATED,
    response_model=WishlistResponse,
)
async def add_wishlist(
    tenant_id: UUID,
    body: WishlistAddRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> WishlistResponse:
    user, _session, _credential = auth
    await service.add_wishlist(
        tenant_id=tenant_id, caller_user_id=user.id, product_id=UUID(body.product_id)
    )
    return await list_wishlist(tenant_id, auth, service)


@router.delete("/tenants/{tenant_id}/wishlist/{product_id}", status_code=status.HTTP_200_OK)
async def remove_wishlist(
    tenant_id: UUID,
    product_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> dict[str, str]:
    user, _session, _credential = auth
    await service.remove_wishlist(
        tenant_id=tenant_id, caller_user_id=user.id, product_id=product_id
    )
    return {"status": "removed"}


@router.get("/tenants/{tenant_id}/cart", response_model=CartResponse)
async def get_cart(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> CartResponse:
    user, _session, _credential = auth
    return _cart(await service.get_cart(tenant_id=tenant_id, caller_user_id=user.id))


@router.post("/tenants/{tenant_id}/cart/lines", response_model=CartResponse)
async def add_cart_line(
    tenant_id: UUID,
    body: AddCartLineRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> CartResponse:
    user, _session, _credential = auth
    view = await service.add_line(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        offering_id=UUID(body.offering_id),
        quantity=body.quantity,
    )
    return _cart(view)


@router.patch("/tenants/{tenant_id}/cart/lines/{line_id}", response_model=CartResponse)
async def update_cart_line(
    tenant_id: UUID,
    line_id: UUID,
    body: UpdateCartLineRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> CartResponse:
    user, _session, _credential = auth
    view = await service.update_line(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        line_id=line_id,
        quantity=body.quantity,
    )
    return _cart(view)


@router.delete("/tenants/{tenant_id}/cart/lines/{line_id}", response_model=CartResponse)
async def remove_cart_line(
    tenant_id: UUID,
    line_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> CartResponse:
    user, _session, _credential = auth
    view = await service.remove_line(
        tenant_id=tenant_id, caller_user_id=user.id, line_id=line_id
    )
    return _cart(view)


@router.get("/tenants/{tenant_id}/addresses", response_model=AddressListResponse)
async def list_addresses(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> AddressListResponse:
    user, _session, _credential = auth
    items = await service.list_addresses(tenant_id=tenant_id, caller_user_id=user.id)
    return AddressListResponse(addresses=[_address(item) for item in items])


@router.post(
    "/tenants/{tenant_id}/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_address(
    tenant_id: UUID,
    body: AddressRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> AddressResponse:
    user, _session, _credential = auth
    item = await service.create_address(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        label=body.label,
        contact_name=body.contact_name,
        line1=body.line1,
        city=body.city,
        state=body.state,
        pincode=body.pincode,
        phone=body.phone,
    )
    return _address(item)


@router.patch("/tenants/{tenant_id}/addresses/{address_id}", response_model=AddressResponse)
async def update_address(
    tenant_id: UUID,
    address_id: UUID,
    body: AddressPatchRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> AddressResponse:
    user, _session, _credential = auth
    item = await service.update_address(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        address_id=address_id,
        fields=body.model_dump(),
    )
    return _address(item)


@router.delete("/tenants/{tenant_id}/addresses/{address_id}")
async def delete_address(
    tenant_id: UUID,
    address_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> dict[str, str]:
    user, _session, _credential = auth
    await service.delete_address(
        tenant_id=tenant_id, caller_user_id=user.id, address_id=address_id
    )
    return {"status": "removed"}


@router.post(
    "/tenants/{tenant_id}/orders",
    response_model=PlaceOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def place_order(
    tenant_id: UUID,
    body: PlaceOrderRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> PlaceOrderResponse:
    user, _session, _credential = auth
    result = await service.place_order(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        caller_principal_id=user.principal_id,
        address_id=UUID(body.address_id) if body.address_id else None,
        payment_method=body.payment_method,
        request_id=x_request_id,
    )
    return PlaceOrderResponse(
        order_id=str(result.order_id),
        status=result.status,
        line_count=result.line_count,
    )


@router.get("/tenants/{tenant_id}/orders", response_model=OrderListResponse)
async def list_orders(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> OrderListResponse:
    user, _session, _credential = auth
    orders = await service.list_orders(tenant_id=tenant_id, caller_user_id=user.id)
    return OrderListResponse(
        orders=[
            OrderSummaryResponse(
                order_id=str(item.order_id),
                status=item.status,
                payment_method=item.payment_method,
                placed_at=item.placed_at,
                line_count=item.line_count,
                total=item.total,
            )
            for item in orders
        ]
    )


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def order_detail(
    order_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> OrderDetailResponse:
    user, _session, _credential = auth
    detail = await service.order_detail(order_id=order_id, caller_user_id=user.id)
    return OrderDetailResponse(
        order_id=str(detail.order_id),
        status=detail.status,
        payment_method=detail.payment_method,
        address_id=str(detail.address_id) if detail.address_id else None,
        placed_at=detail.placed_at,
        tracking=None,
        lines=[
            OrderLineResponse(
                line_id=str(line.line_id),
                offering_id=str(line.offering_id),
                product_name=line.product_name,
                plan_name=line.plan_name,
                quantity=line.quantity,
                fulfilment_type=line.fulfilment_type,
                billing_period=line.billing_period,
                unit_price=line.unit_price,
                status=line.status,
            )
            for line in detail.lines
        ],
    )


@router.post(
    "/orders/{order_id}/returns",
    response_model=ReturnResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_return(
    order_id: UUID,
    body: ReturnRequest,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> ReturnResponse:
    user, _session, _credential = auth
    item = await service.request_return(
        order_id=order_id,
        caller_user_id=user.id,
        line_id=UUID(body.line_id),
        reason=body.reason,
        notes=body.notes,
    )
    return ReturnResponse(
        return_id=str(item.return_id),
        order_id=str(item.order_id),
        line_id=str(item.line_id),
        product_name=item.product_name,
        reason=item.reason,
        status=item.status,
    )


@router.get("/tenants/{tenant_id}/returns", response_model=ReturnListResponse)
async def list_returns(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
) -> ReturnListResponse:
    user, _session, _credential = auth
    items = await service.list_returns(tenant_id=tenant_id, caller_user_id=user.id)
    return ReturnListResponse(
        returns=[
            ReturnResponse(
                return_id=str(item.return_id),
                order_id=str(item.order_id),
                line_id=str(item.line_id),
                product_name=item.product_name,
                reason=item.reason,
                status=item.status,
            )
            for item in items
        ]
    )


@router.get("/tenants/{tenant_id}/subscriptions", response_model=SubscriptionListResponse)
async def list_subscriptions(
    tenant_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> SubscriptionListResponse:
    user, _session, _credential = auth
    items = await service.list_subscriptions(
        tenant_id=tenant_id,
        caller_principal_id=user.principal_id,
        request_id=x_request_id,
    )
    active = sum(1 for item in items if item.status == "active")
    return SubscriptionListResponse(
        subscriptions=[
            SubscriptionResponse(
                offering_id=str(item.offering_id),
                product_name=item.product_name,
                plan_name=item.plan_name,
                status=item.status,
                next_billing_at=item.next_billing_at,
            )
            for item in items
        ],
        active_count=active,
    )


@router.post(
    "/tenants/{tenant_id}/subscriptions/{offering_id}/cancel",
    response_model=SubscriptionResponse,
)
async def cancel_subscription(
    tenant_id: UUID,
    offering_id: UUID,
    auth: CurrentAuthDep,
    service: Annotated[CommerceService, Depends(get_commerce_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> SubscriptionResponse:
    user, _session, _credential = auth
    item = await service.cancel_subscription(
        tenant_id=tenant_id,
        caller_user_id=user.id,
        caller_principal_id=user.principal_id,
        offering_id=offering_id,
        request_id=x_request_id,
    )
    return SubscriptionResponse(
        offering_id=str(item.offering_id),
        product_name=item.product_name,
        plan_name=item.plan_name,
        status=item.status,
        next_billing_at=item.next_billing_at,
    )
