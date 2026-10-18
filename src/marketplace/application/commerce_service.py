from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from authz.application.authorization_service import AuthorizationService
from authz.domain.deny_messages import public_forbid_detail
from authz.domain.models import ApiSurface, AuthorizeCommand
from identity.domain.security import utcnow
from marketplace.application.access import audit, require_vendor_owner
from marketplace.domain.fulfilment import ADDRESS_REQUIRED, PROVISION_TYPES
from marketplace.infrastructure.models import (
    CartLineRow,
    CartRow,
    InstallationRow,
    OfferingRow,
    OrderLineRow,
    OrderRow,
    PayoutLedgerRow,
    ProductReviewRow,
    ProductRow,
    ReturnRow,
    VendorFulfilmentRow,
    WishlistRow,
)
from platform_ops.infrastructure.models import PlatformConfigRow
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import AddressRow, TenantMembershipRow, TenantRow
from vendor.infrastructure.models import VendorProfileRow, VendorSettingsRow

PAYMENT_METHODS = frozenset({"upi", "card", "netbanking"})


@dataclass(frozen=True, slots=True)
class WishlistItem:
    product_id: UUID
    name: str
    vendor_name: str
    fulfilment_type: str


@dataclass(frozen=True, slots=True)
class CartLineView:
    line_id: UUID
    offering_id: UUID
    product_id: UUID
    product_name: str
    plan_name: str
    quantity: int
    unit_price: float
    fulfilment_type: str
    billing_period: str
    vendor_id: UUID
    vendor_name: str
    currency: str = "INR"


@dataclass(frozen=True, slots=True)
class CartView:
    cart_id: UUID | None
    status: str
    lines: list[CartLineView]


@dataclass(frozen=True, slots=True)
class AddressView:
    address_id: UUID
    label: str
    contact_name: str
    line1: str
    city: str
    state: str
    pincode: str
    phone: str


@dataclass(frozen=True, slots=True)
class OrderPlaced:
    order_id: UUID
    status: str
    line_count: int


@dataclass(frozen=True, slots=True)
class OrderVendorSummary:
    vendor_id: UUID
    vendor_name: str
    status: str


@dataclass(frozen=True, slots=True)
class OrderSummary:
    order_id: UUID
    status: str
    payment_method: str
    placed_at: str
    line_count: int
    total: float
    vendors: list[OrderVendorSummary]


@dataclass(frozen=True, slots=True)
class VendorOrderLine:
    order_id: UUID
    line_id: UUID
    product_name: str
    quantity: int
    fulfilment_type: str
    unit_price: float
    total: float
    status: str
    placed_at: str
    customer_name: str
    line1: str
    city: str
    state: str
    pincode: str
    phone: str
    courier: str
    tracking_number: str
    currency: str = "INR"
    refund_status: str = "none"
    refund_amount: float | None = None


FULFILMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "placed": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"processing"}),
    "processing": frozenset({"ready_to_ship", "delayed"}),
    "delayed": frozenset({"ready_to_ship"}),
    "ready_to_ship": frozenset({"shipped"}),
    "shipped": frozenset({"delivered"}),
}


@dataclass(frozen=True, slots=True)
class VendorCustomer:
    tenant_id: UUID
    customer_name: str
    order_count: int
    total: float
    last_order_at: str
    city: str = ""
    currency: str = "INR"
    segment: str = "New"


@dataclass(frozen=True, slots=True)
class VendorReview:
    review_id: UUID
    customer_name: str
    product_name: str
    rating: int
    comment: str
    created_at: str


@dataclass(frozen=True, slots=True)
class CreatedReview:
    review_id: UUID
    order_id: UUID
    line_id: UUID
    product_name: str
    rating: int
    comment: str


REFUND_METHODS = frozenset({"original", "wallet", "upi"})


def customer_segment(order_count: int) -> str:
    if order_count >= 8:
        return "VIP"
    if order_count >= 3:
        return "Regular"
    return "New"


@dataclass(frozen=True, slots=True)
class VendorReturn:
    return_id: UUID
    order_id: UUID
    line_id: UUID
    product_name: str
    reason: str
    notes: str
    status: str
    created_at: str
    customer_name: str
    quantity: int = 1
    amount: float = 0.0
    currency: str = "INR"
    refund_amount: float | None = None
    refund_currency: str = "INR"
    refund_method: str | None = None
    vendor_notes: str = ""
    decided_at: str = ""
    refunded_at: str = ""


@dataclass(frozen=True, slots=True)
class PayoutView:
    settlement_id: str
    period: str
    gross: float
    platform_fee: float
    net: float
    status: str


@dataclass(frozen=True, slots=True)
class PayoutSummary:
    earned_this_month: float
    next_settlement: float | None
    next_settlement_due_days: int | None
    commission_this_month: float
    commission_rate_pct: int
    total_settled: float


@dataclass(frozen=True, slots=True)
class PayoutListResult:
    payouts: list[PayoutView]
    summary: PayoutSummary


def settlement_id_for(payout_id: UUID) -> str:
    return f"SET-{payout_id.hex[-6:].upper()}"


@dataclass(frozen=True, slots=True)
class OrderLineView:
    line_id: UUID
    offering_id: UUID
    product_name: str
    plan_name: str
    quantity: int
    fulfilment_type: str
    billing_period: str
    unit_price: float
    status: str
    vendor_id: UUID
    vendor_name: str
    currency: str = "INR"


@dataclass(frozen=True, slots=True)
class TimelineStep:
    label: str
    at: str
    done: bool


@dataclass(frozen=True, slots=True)
class OrderVendorSlice:
    vendor_id: UUID
    vendor_name: str
    status: str
    courier: str
    tracking_number: str
    refund_status: str
    refund_amount: float | None
    lines: list[OrderLineView]


@dataclass(frozen=True, slots=True)
class OrderDetail:
    order_id: UUID
    status: str
    payment_method: str
    address_id: UUID | None
    placed_at: str
    lines: list[OrderLineView]
    vendors: list[OrderVendorSlice]
    address: AddressView | None
    timeline: list[TimelineStep]
    tracking: None = None


@dataclass(frozen=True, slots=True)
class ReturnView:
    return_id: UUID
    order_id: UUID
    line_id: UUID
    product_name: str
    reason: str
    status: str


@dataclass(frozen=True, slots=True)
class SubscriptionView:
    offering_id: UUID
    product_name: str
    plan_name: str
    status: str
    next_billing_at: str | None


class CommerceService:
    """J43 wishlist, J44 cart, J48–J52 checkout, orders, returns, subscriptions, addresses."""

    def __init__(self, session: AsyncSession, authorization: AuthorizationService) -> None:
        self._session = session
        self._authorization = authorization

    async def list_wishlist(self, *, tenant_id: UUID, caller_user_id: UUID) -> list[WishlistItem]:
        await self._require_member(tenant_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(WishlistRow, ProductRow, VendorProfileRow)
                .join(ProductRow, ProductRow.id == WishlistRow.product_id)
                .join(VendorProfileRow, VendorProfileRow.id == ProductRow.vendor_id)
                .where(WishlistRow.tenant_id == tenant_id)
                .order_by(WishlistRow.created_at.desc())
            )
        ).all()
        return [
            WishlistItem(
                product_id=product.id,
                name=product.name,
                vendor_name=vendor.legal_name,
                fulfilment_type=product.fulfilment_type,
            )
            for _wish, product, vendor in rows
        ]

    async def add_wishlist(
        self, *, tenant_id: UUID, caller_user_id: UUID, product_id: UUID
    ) -> None:
        await self._require_member(tenant_id, caller_user_id)
        product = await self._published_product(product_id)
        existing = (
            await self._session.execute(
                select(WishlistRow.id).where(
                    WishlistRow.tenant_id == tenant_id,
                    WishlistRow.product_id == product.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("already saved")
        self._session.add(
            WishlistRow(id=uuid.uuid4(), tenant_id=tenant_id, product_id=product.id)
        )
        await self._session.commit()

    async def remove_wishlist(
        self, *, tenant_id: UUID, caller_user_id: UUID, product_id: UUID
    ) -> None:
        await self._require_member(tenant_id, caller_user_id)
        row = (
            await self._session.execute(
                select(WishlistRow).where(
                    WishlistRow.tenant_id == tenant_id,
                    WishlistRow.product_id == product_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise NotFoundError("wishlist item not found")
        await self._session.delete(row)
        await self._session.commit()

    async def get_cart(self, *, tenant_id: UUID, caller_user_id: UUID) -> CartView:
        await self._require_member(tenant_id, caller_user_id)
        cart = await self._open_cart(tenant_id)
        if cart is None:
            return CartView(cart_id=None, status="open", lines=[])
        return CartView(cart_id=cart.id, status=cart.status, lines=await self._cart_lines(cart.id))

    async def add_line(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        offering_id: UUID,
        quantity: int,
    ) -> CartView:
        await self._require_member(tenant_id, caller_user_id)
        self._check_quantity(quantity)
        offering, product = await self._published_offering(offering_id)
        if product.fulfilment_type in PROVISION_TYPES:
            raise ConflictError("software and cloud offerings are installed, not added to the cart")
        cart = await self._open_cart(tenant_id)
        if cart is None:
            cart = CartRow(id=uuid.uuid4(), tenant_id=tenant_id, status="open")
            self._session.add(cart)
            await self._session.flush()
        existing = (
            await self._session.execute(
                select(CartLineRow).where(
                    CartLineRow.cart_id == cart.id,
                    CartLineRow.offering_id == offering.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("line already present")
        self._session.add(
            CartLineRow(
                id=uuid.uuid4(),
                cart_id=cart.id,
                offering_id=offering.id,
                quantity=quantity,
            )
        )
        await self._session.commit()
        return CartView(cart_id=cart.id, status=cart.status, lines=await self._cart_lines(cart.id))

    async def update_line(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        line_id: UUID,
        quantity: int,
    ) -> CartView:
        await self._require_member(tenant_id, caller_user_id)
        self._check_quantity(quantity)
        cart = await self._open_cart(tenant_id)
        line = await self._line_on_cart(cart, line_id)
        line.quantity = quantity
        await self._session.commit()
        assert cart is not None
        return CartView(cart_id=cart.id, status=cart.status, lines=await self._cart_lines(cart.id))

    async def remove_line(
        self, *, tenant_id: UUID, caller_user_id: UUID, line_id: UUID
    ) -> CartView:
        await self._require_member(tenant_id, caller_user_id)
        cart = await self._open_cart(tenant_id)
        line = await self._line_on_cart(cart, line_id)
        await self._session.delete(line)
        await self._session.commit()
        assert cart is not None
        return CartView(cart_id=cart.id, status=cart.status, lines=await self._cart_lines(cart.id))

    async def list_addresses(self, *, tenant_id: UUID, caller_user_id: UUID) -> list[AddressView]:
        await self._require_member(tenant_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(AddressRow)
                .where(AddressRow.tenant_id == tenant_id, AddressRow.status == "active")
                .order_by(AddressRow.created_at.desc())
            )
        ).scalars().all()
        return [self._address_view(row) for row in rows]

    async def create_address(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        label: str,
        contact_name: str,
        line1: str,
        city: str,
        state: str,
        pincode: str,
        phone: str,
    ) -> AddressView:
        await self._require_member(tenant_id, caller_user_id)
        fields = {
            "label": label,
            "contact_name": contact_name,
            "line1": line1,
            "city": city,
            "state": state,
            "pincode": pincode,
            "phone": phone,
        }
        cleaned = {key: value.strip() for key, value in fields.items()}
        if any(not value for value in cleaned.values()):
            raise ValidationError("address fields are required")
        row = AddressRow(id=uuid.uuid4(), tenant_id=tenant_id, status="active", **cleaned)
        self._session.add(row)
        await self._session.commit()
        return self._address_view(row)

    async def update_address(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        address_id: UUID,
        fields: dict[str, str | None],
    ) -> AddressView:
        await self._require_member(tenant_id, caller_user_id)
        row = await self._address(tenant_id, address_id)
        for key, value in fields.items():
            if value is None:
                continue
            cleaned = value.strip()
            if not cleaned:
                raise ValidationError(f"{key} is required")
            setattr(row, key, cleaned)
        await self._session.commit()
        return self._address_view(row)

    async def delete_address(
        self, *, tenant_id: UUID, caller_user_id: UUID, address_id: UUID
    ) -> None:
        await self._require_member(tenant_id, caller_user_id)
        row = await self._address(tenant_id, address_id)
        blocking = (
            await self._session.execute(
                select(OrderRow.id).where(
                    OrderRow.address_id == row.id,
                    OrderRow.status != "fulfilled",
                )
            )
        ).scalar_one_or_none()
        if blocking is not None:
            raise ConflictError("address is on an open order")
        await self._session.delete(row)
        await self._session.commit()

    async def place_order(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        caller_principal_id: UUID,
        address_id: UUID | None,
        payment_method: str,
        request_id: str | None,
    ) -> OrderPlaced:
        await self._require_permission(
            caller_principal_id, tenant_id, "resource.create", request_id
        )
        method = payment_method.strip().lower()
        if method not in PAYMENT_METHODS:
            raise ValidationError("payment_method must be upi, card, or netbanking")
        cart = await self._open_cart(tenant_id)
        if cart is None:
            raise ConflictError("cart empty")
        lines = await self._cart_line_rows(cart.id)
        if not lines:
            raise ConflictError("cart empty")
        needs_address = any(product.fulfilment_type in ADDRESS_REQUIRED for _line, _offering, product in lines)
        address: AddressRow | None = None
        if needs_address:
            if address_id is None:
                raise ValidationError("address_id is required for this cart")
            address = await self._address(tenant_id, address_id)
        elif address_id is not None:
            address = await self._address(tenant_id, address_id)
        order = OrderRow(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            cart_id=cart.id,
            address_id=address.id if address else None,
            payment_method=method,
            status="placed",
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
                    status="active",
                )
            )
            vendor_ids.add(product.vendor_id)
        for vendor_id in vendor_ids:
            self._session.add(
                VendorFulfilmentRow(
                    id=uuid.uuid4(),
                    order_id=order.id,
                    vendor_id=vendor_id,
                    status="placed",
                    refund_status="none",
                )
            )
        cart.status = "checked_out"
        await audit(
            self._session,
            action="order.placed",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={
                "order_id": str(order.id),
                "cart_id": str(cart.id),
                "line_count": len(lines),
                "payment_method": method,
            },
        )
        await self._session.commit()
        return OrderPlaced(order_id=order.id, status=order.status, line_count=len(lines))

    async def list_orders(self, *, tenant_id: UUID, caller_user_id: UUID) -> list[OrderSummary]:
        await self._require_member(tenant_id, caller_user_id)
        orders = (
            await self._session.execute(
                select(OrderRow)
                .where(OrderRow.tenant_id == tenant_id)
                .order_by(OrderRow.created_at.desc())
            )
        ).scalars().all()
        summaries: list[OrderSummary] = []
        for order in orders:
            lines = (
                await self._session.execute(
                    select(OrderLineRow).where(OrderLineRow.order_id == order.id)
                )
            ).scalars().all()
            total = sum(float(line.unit_price) * line.quantity for line in lines)
            vendor_rows = (
                await self._session.execute(
                    select(VendorFulfilmentRow, VendorProfileRow)
                    .join(VendorProfileRow, VendorProfileRow.id == VendorFulfilmentRow.vendor_id)
                    .where(VendorFulfilmentRow.order_id == order.id)
                    .order_by(VendorProfileRow.legal_name.asc())
                )
            ).all()
            summaries.append(
                OrderSummary(
                    order_id=order.id,
                    status=order.status,
                    payment_method=order.payment_method,
                    placed_at=order.created_at.isoformat() if order.created_at else "",
                    line_count=len(lines),
                    total=total,
                    vendors=[
                        OrderVendorSummary(
                            vendor_id=fulfilment.vendor_id,
                            vendor_name=vendor.legal_name,
                            status=fulfilment.status,
                        )
                        for fulfilment, vendor in vendor_rows
                    ],
                )
            )
        return summaries

    async def list_vendor_orders(
        self, *, vendor_id: UUID, caller_user_id: UUID, status: str | None = None
    ) -> list[VendorOrderLine]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        statement = (
            select(OrderLineRow, OrderRow, TenantRow, AddressRow, VendorFulfilmentRow)
            .join(OrderRow, OrderRow.id == OrderLineRow.order_id)
            .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
            .join(ProductRow, ProductRow.id == OfferingRow.product_id)
            .join(TenantRow, TenantRow.id == OrderRow.tenant_id)
            .outerjoin(AddressRow, AddressRow.id == OrderRow.address_id)
            .outerjoin(
                VendorFulfilmentRow,
                and_(
                    VendorFulfilmentRow.order_id == OrderRow.id,
                    VendorFulfilmentRow.vendor_id == vendor_id,
                ),
            )
            .where(ProductRow.vendor_id == vendor_id)
            .order_by(OrderRow.created_at.desc())
        )
        if status:
            wanted = status.strip()
            if wanted == "placed":
                statement = statement.where(
                    or_(VendorFulfilmentRow.status.is_(None), VendorFulfilmentRow.status == "placed")
                )
            else:
                statement = statement.where(VendorFulfilmentRow.status == wanted)
        rows = (await self._session.execute(statement)).all()
        return [
            VendorOrderLine(
                order_id=order.id,
                line_id=line.id,
                product_name=line.product_name,
                quantity=line.quantity,
                fulfilment_type=line.fulfilment_type,
                unit_price=float(line.unit_price),
                total=float(line.unit_price) * line.quantity,
                status=fulfilment.status if fulfilment is not None else "placed",
                placed_at=order.created_at.isoformat() if order.created_at else "",
                customer_name=address.contact_name if address is not None else tenant.name,
                line1=address.line1 if address is not None else "",
                city=address.city if address is not None else "",
                state=address.state if address is not None else "",
                pincode=address.pincode if address is not None else "",
                phone=address.phone if address is not None else "",
                courier=fulfilment.courier if fulfilment is not None else "",
                tracking_number=fulfilment.tracking_number if fulfilment is not None else "",
                currency=getattr(line, "currency", None) or "INR",
                refund_status=fulfilment.refund_status if fulfilment is not None else "none",
                refund_amount=(
                    float(fulfilment.refund_amount)
                    if fulfilment is not None and fulfilment.refund_amount is not None
                    else None
                ),
            )
            for line, order, tenant, address, fulfilment in rows
        ]

    async def advance_vendor_order(
        self,
        *,
        vendor_id: UUID,
        order_id: UUID,
        caller_user_id: UUID,
        status: str,
        courier: str,
        tracking_number: str,
    ) -> VendorFulfilmentRow:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        owned = (
            await self._session.execute(
                select(OrderLineRow.id)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(OrderLineRow.order_id == order_id, ProductRow.vendor_id == vendor_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if owned is None:
            raise NotFoundError("order not found")
        order = await self._session.get(OrderRow, order_id)
        if order is None:
            raise NotFoundError("order not found")
        current = (
            await self._session.execute(
                select(VendorFulfilmentRow).where(
                    VendorFulfilmentRow.order_id == order_id,
                    VendorFulfilmentRow.vendor_id == vendor_id,
                )
            )
        ).scalar_one_or_none()
        current_status = current.status if current is not None else "placed"
        if status not in FULFILMENT_TRANSITIONS.get(current_status, frozenset()):
            raise ValidationError(f"cannot move an order from {current_status} to {status}")
        cleaned_courier = courier.strip()
        cleaned_tracking = tracking_number.strip()
        if status == "shipped" and (not cleaned_courier or not cleaned_tracking):
            raise ValidationError("courier and tracking number are required")
        if current is None:
            current = VendorFulfilmentRow(
                id=uuid.uuid4(),
                order_id=order_id,
                vendor_id=vendor_id,
                status=status,
                courier=cleaned_courier if status == "shipped" else "",
                tracking_number=cleaned_tracking if status == "shipped" else "",
                refund_status="none",
            )
            self._session.add(current)
        else:
            current.status = status
            if status == "shipped":
                current.courier = cleaned_courier
                current.tracking_number = cleaned_tracking
            current.updated_at = utcnow()
        vendor_line_total = await self._vendor_line_total(order_id, vendor_id)
        if status == "cancelled":
            current.refund_status = "pending"
            current.refund_amount = Decimal(str(vendor_line_total))
            await audit(
                self._session,
                action="order.vendor_rejected",
                actor_user_id=caller_user_id,
                tenant_id=order.tenant_id,
                payload={
                    "order_id": str(order_id),
                    "vendor_id": str(vendor_id),
                    "refund_amount": vendor_line_total,
                },
            )
        await audit(
            self._session,
            action="order.fulfilment_updated",
            actor_user_id=caller_user_id,
            tenant_id=order.tenant_id,
            payload={
                "order_id": str(order_id),
                "vendor_id": str(vendor_id),
                "status": status,
            },
        )
        await self._rollup_order_status(order_id)
        await self._session.commit()
        return current

    async def issue_vendor_reject_refund(
        self, *, vendor_id: UUID, order_id: UUID, caller_user_id: UUID
    ) -> VendorFulfilmentRow:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        fulfilment = (
            await self._session.execute(
                select(VendorFulfilmentRow).where(
                    VendorFulfilmentRow.order_id == order_id,
                    VendorFulfilmentRow.vendor_id == vendor_id,
                )
            )
        ).scalar_one_or_none()
        if fulfilment is None:
            raise NotFoundError("order not found")
        if fulfilment.status != "cancelled" or fulfilment.refund_status != "pending":
            raise ConflictError("refund is not pending for a cancelled vendor slice")
        order = await self._session.get(OrderRow, order_id)
        if order is None:
            raise NotFoundError("order not found")
        fulfilment.refund_status = "refunded"
        fulfilment.updated_at = utcnow()
        await audit(
            self._session,
            action="order.vendor_reject_refunded",
            actor_user_id=caller_user_id,
            tenant_id=order.tenant_id,
            payload={
                "order_id": str(order_id),
                "vendor_id": str(vendor_id),
                "refund_amount": (
                    float(fulfilment.refund_amount) if fulfilment.refund_amount is not None else None
                ),
            },
        )
        await self._session.commit()
        return fulfilment

    async def cancel_order(
        self, *, tenant_id: UUID, order_id: UUID, caller_user_id: UUID
    ) -> OrderDetail:
        await self._require_member(tenant_id, caller_user_id)
        order = await self._session.get(OrderRow, order_id)
        if order is None or order.tenant_id != tenant_id:
            raise NotFoundError("order not found")
        fulfilments = (
            await self._session.execute(
                select(VendorFulfilmentRow).where(VendorFulfilmentRow.order_id == order_id)
            )
        ).scalars().all()
        if any(row.status != "placed" for row in fulfilments):
            raise ConflictError("order can only be cancelled while all vendors are still placed")
        for fulfilment in fulfilments:
            total = await self._vendor_line_total(order_id, fulfilment.vendor_id)
            fulfilment.status = "cancelled"
            fulfilment.refund_status = "pending"
            fulfilment.refund_amount = Decimal(str(total))
            fulfilment.updated_at = utcnow()
        order.status = "cancelled"
        await audit(
            self._session,
            action="order.cancelled_by_buyer",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={"order_id": str(order_id)},
        )
        await self._session.commit()
        return await self.order_detail(order_id=order_id, caller_user_id=caller_user_id)

    async def _rollup_order_status(self, order_id: UUID) -> None:
        order = await self._session.get(OrderRow, order_id)
        if order is None:
            return
        statuses = [
            row.status
            for row in (
                await self._session.execute(
                    select(VendorFulfilmentRow).where(VendorFulfilmentRow.order_id == order_id)
                )
            ).scalars().all()
        ]
        if not statuses:
            return
        all_cancelled = all(status == "cancelled" for status in statuses)
        all_delivered = all(status == "delivered" for status in statuses)
        any_cancelled = any(status == "cancelled" for status in statuses)
        any_delivered = any(status == "delivered" for status in statuses)
        all_placed = all(status == "placed" for status in statuses)
        if all_cancelled:
            order.status = "cancelled"
        elif all_delivered:
            order.status = "delivered"
        elif any_cancelled and any(status != "cancelled" for status in statuses):
            order.status = "partial"
        elif any_delivered and any(status != "delivered" for status in statuses):
            order.status = "partial"
        elif all_placed:
            order.status = "placed"
        else:
            order.status = "processing"

    async def _vendor_line_total(self, order_id: UUID, vendor_id: UUID) -> float:
        lines = (
            await self._session.execute(
                select(OrderLineRow)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(OrderLineRow.order_id == order_id, ProductRow.vendor_id == vendor_id)
            )
        ).scalars().all()
        return sum(float(line.unit_price) * line.quantity for line in lines)

    async def list_vendor_customers(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[VendorCustomer]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        currency = await self.vendor_payout_currency(
            vendor_id=vendor_id, caller_user_id=caller_user_id
        )
        rows = (
            await self._session.execute(
                select(OrderLineRow, OrderRow, TenantRow, AddressRow)
                .join(OrderRow, OrderRow.id == OrderLineRow.order_id)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .join(TenantRow, TenantRow.id == OrderRow.tenant_id)
                .outerjoin(AddressRow, AddressRow.id == OrderRow.address_id)
                .where(ProductRow.vendor_id == vendor_id)
            )
        ).all()
        grouped: dict[UUID, dict] = {}
        for line, order, tenant, address in rows:
            bucket = grouped.get(tenant.id)
            placed = order.created_at.isoformat() if order.created_at else ""
            name = address.contact_name if address is not None else tenant.name
            city = address.city if address is not None else ""
            if bucket is None:
                grouped[tenant.id] = {
                    "name": name,
                    "city": city,
                    "orders": {order.id},
                    "total": float(line.unit_price) * line.quantity,
                    "last": placed,
                }
                continue
            bucket["orders"].add(order.id)
            bucket["total"] += float(line.unit_price) * line.quantity
            if placed >= bucket["last"]:
                bucket["last"] = placed
                bucket["name"] = name
                bucket["city"] = city
        customers = [
            VendorCustomer(
                tenant_id=tenant_id,
                customer_name=bucket["name"],
                order_count=len(bucket["orders"]),
                total=bucket["total"],
                last_order_at=bucket["last"],
                city=bucket.get("city") or "",
                currency=currency,
                segment=customer_segment(len(bucket["orders"])),
            )
            for tenant_id, bucket in grouped.items()
        ]
        customers.sort(key=lambda item: item.last_order_at, reverse=True)
        return customers

    async def create_review(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        order_id: UUID,
        line_id: UUID,
        rating: int,
        comment: str,
    ) -> CreatedReview:
        await self._require_member(tenant_id, caller_user_id)
        if rating < 1 or rating > 5:
            raise ValidationError("rating must be between 1 and 5")
        order = await self._session.get(OrderRow, order_id)
        if order is None or order.tenant_id != tenant_id:
            raise NotFoundError("order not found")
        line = await self._session.get(OrderLineRow, line_id)
        if line is None or line.order_id != order.id:
            raise NotFoundError("order line not found")
        existing = (
            await self._session.execute(
                select(ProductReviewRow.id).where(ProductReviewRow.line_id == line.id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("this line already has a review")
        product = (
            await self._session.execute(
                select(ProductRow)
                .join(OfferingRow, OfferingRow.product_id == ProductRow.id)
                .where(OfferingRow.id == line.offering_id)
            )
        ).scalar_one_or_none()
        if product is None:
            raise NotFoundError("product not found")
        row = ProductReviewRow(
            id=uuid.uuid4(),
            vendor_id=product.vendor_id,
            product_id=product.id,
            order_id=order.id,
            line_id=line.id,
            tenant_id=tenant_id,
            rating=rating,
            comment=comment.strip(),
        )
        self._session.add(row)
        await audit(
            self._session,
            action="review.created",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={
                "review_id": str(row.id),
                "order_id": str(order.id),
                "line_id": str(line.id),
                "rating": rating,
            },
        )
        await self._session.commit()
        return CreatedReview(
            review_id=row.id,
            order_id=order.id,
            line_id=line.id,
            product_name=line.product_name,
            rating=row.rating,
            comment=row.comment,
        )

    async def list_vendor_reviews(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[VendorReview]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(ProductReviewRow, OrderLineRow, OrderRow, TenantRow, AddressRow)
                .join(OrderLineRow, OrderLineRow.id == ProductReviewRow.line_id)
                .join(OrderRow, OrderRow.id == ProductReviewRow.order_id)
                .join(TenantRow, TenantRow.id == ProductReviewRow.tenant_id)
                .outerjoin(AddressRow, AddressRow.id == OrderRow.address_id)
                .where(ProductReviewRow.vendor_id == vendor_id)
                .order_by(ProductReviewRow.created_at.desc())
            )
        ).all()
        reviews: list[VendorReview] = []
        for review, line, order, tenant, address in rows:
            name = address.contact_name if address is not None else tenant.name
            reviews.append(
                VendorReview(
                    review_id=review.id,
                    customer_name=name,
                    product_name=line.product_name,
                    rating=review.rating,
                    comment=review.comment,
                    created_at=review.created_at.isoformat() if review.created_at else "",
                )
            )
        return reviews

    async def list_vendor_returns(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[VendorReturn]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(ReturnRow, OrderLineRow, OrderRow, TenantRow, AddressRow)
                .join(OrderLineRow, OrderLineRow.id == ReturnRow.line_id)
                .join(OrderRow, OrderRow.id == ReturnRow.order_id)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .join(TenantRow, TenantRow.id == OrderRow.tenant_id)
                .outerjoin(AddressRow, AddressRow.id == OrderRow.address_id)
                .where(ProductRow.vendor_id == vendor_id)
                .order_by(ReturnRow.created_at.desc())
            )
        ).all()
        return [
            VendorReturn(
                return_id=item.id,
                order_id=item.order_id,
                line_id=item.line_id,
                product_name=line.product_name,
                reason=item.reason,
                notes=item.notes,
                status=item.status,
                created_at=item.created_at.isoformat() if item.created_at else "",
                customer_name=address.contact_name if address is not None else tenant.name,
                quantity=line.quantity,
                amount=float(line.unit_price) * line.quantity,
                currency=getattr(line, "currency", None) or "INR",
                refund_amount=float(item.refund_amount) if item.refund_amount is not None else None,
                refund_currency=getattr(item, "refund_currency", None) or "INR",
                refund_method=item.refund_method,
                vendor_notes=item.vendor_notes or "",
                decided_at=item.decided_at.isoformat() if item.decided_at else "",
                refunded_at=item.refunded_at.isoformat() if item.refunded_at else "",
            )
            for item, line, _order, tenant, address in rows
        ]

    async def decide_vendor_return(
        self,
        *,
        vendor_id: UUID,
        return_id: UUID,
        caller_user_id: UUID,
        decision: str,
        refund_amount: Decimal | None = None,
        refund_method: str | None = None,
        vendor_notes: str | None = None,
    ) -> VendorReturn:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        row, line = await self._vendor_return_row(vendor_id=vendor_id, return_id=return_id)
        if row.status != "requested":
            raise ConflictError("return is not awaiting review")
        cleaned_decision = decision.strip().lower()
        if cleaned_decision not in ("approved", "rejected"):
            raise ValidationError("decision must be approved or rejected")
        notes = (vendor_notes or "").strip()
        row.vendor_notes = notes
        row.decided_at = utcnow()
        if cleaned_decision == "rejected":
            row.status = "rejected"
            await audit(
                self._session,
                action="return.rejected",
                actor_user_id=caller_user_id,
                payload={"return_id": str(row.id), "vendor_id": str(vendor_id)},
            )
        else:
            line_total = Decimal(str(line.unit_price)) * line.quantity
            if refund_amount is None:
                raise ValidationError("refund_amount is required when approving")
            if refund_amount <= 0 or refund_amount > line_total:
                raise ValidationError("refund_amount must be greater than zero and at most the line total")
            method = (refund_method or "").strip().lower()
            if method not in REFUND_METHODS:
                raise ValidationError(
                    f"refund_method must be one of {', '.join(sorted(REFUND_METHODS))}"
                )
            row.status = "approved"
            row.refund_amount = refund_amount
            row.refund_currency = getattr(line, "currency", None) or "INR"
            row.refund_method = method
            await audit(
                self._session,
                action="return.approved",
                actor_user_id=caller_user_id,
                payload={
                    "return_id": str(row.id),
                    "vendor_id": str(vendor_id),
                    "refund_amount": str(refund_amount),
                    "refund_method": method,
                },
            )
        await self._session.commit()
        returns = await self.list_vendor_returns(vendor_id=vendor_id, caller_user_id=caller_user_id)
        return next(item for item in returns if item.return_id == return_id)

    async def issue_vendor_return_refund(
        self,
        *,
        vendor_id: UUID,
        return_id: UUID,
        caller_user_id: UUID,
    ) -> VendorReturn:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        row, _line = await self._vendor_return_row(vendor_id=vendor_id, return_id=return_id)
        if row.status != "approved":
            raise ConflictError("return must be approved before refunding")
        row.status = "refunded"
        row.refunded_at = utcnow()
        await audit(
            self._session,
            action="return.refunded",
            actor_user_id=caller_user_id,
            payload={
                "return_id": str(row.id),
                "vendor_id": str(vendor_id),
                "refund_amount": str(row.refund_amount) if row.refund_amount is not None else None,
            },
        )
        await self._session.commit()
        returns = await self.list_vendor_returns(vendor_id=vendor_id, caller_user_id=caller_user_id)
        return next(item for item in returns if item.return_id == return_id)

    async def _vendor_return_row(
        self, *, vendor_id: UUID, return_id: UUID
    ) -> tuple[ReturnRow, OrderLineRow]:
        row = (
            await self._session.execute(
                select(ReturnRow, OrderLineRow)
                .join(OrderLineRow, OrderLineRow.id == ReturnRow.line_id)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(ReturnRow.id == return_id, ProductRow.vendor_id == vendor_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("return not found")
        return row[0], row[1]

    async def list_vendor_payouts(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> PayoutListResult:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(PayoutLedgerRow)
                .where(PayoutLedgerRow.vendor_id == vendor_id)
                .order_by(PayoutLedgerRow.created_at.desc(), PayoutLedgerRow.period.desc())
            )
        ).scalars().all()
        now = utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        earned_this_month = 0.0
        commission_this_month = 0.0
        total_settled = 0.0
        next_settlement: float | None = None
        next_settlement_due_days: int | None = None
        payouts: list[PayoutView] = []
        for row in rows:
            created = row.created_at
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created is not None and created >= month_start:
                earned_this_month += float(row.gross)
                commission_this_month += float(row.platform_fee)
            status_l = (row.status or "").lower()
            if status_l == "paid":
                total_settled += float(row.net)
            elif next_settlement is None:
                next_settlement = float(row.net)
                if created is not None:
                    days_since = max(0, (now - created).days)
                    next_settlement_due_days = max(0, 7 - days_since)
                else:
                    next_settlement_due_days = 7
            payouts.append(
                PayoutView(
                    settlement_id=settlement_id_for(row.id),
                    period=row.period,
                    gross=float(row.gross),
                    platform_fee=float(row.platform_fee),
                    net=float(row.net),
                    status=row.status,
                )
            )
        rate = await self._commission_rate_pct()
        return PayoutListResult(
            payouts=payouts,
            summary=PayoutSummary(
                earned_this_month=earned_this_month,
                next_settlement=next_settlement,
                next_settlement_due_days=next_settlement_due_days,
                commission_this_month=commission_this_month,
                commission_rate_pct=rate,
                total_settled=total_settled,
            ),
        )

    async def _commission_rate_pct(self) -> int:
        row = await self._session.get(PlatformConfigRow, "commission_rate_pct")
        if row is None:
            return 10
        value = row.value
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10

    async def vendor_payout_currency(self, *, vendor_id: UUID, caller_user_id: UUID) -> str:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        row = await self._session.get(VendorSettingsRow, vendor_id)
        if row is None or not row.default_currency:
            return "INR"
        return row.default_currency.strip().upper() or "INR"

    async def order_detail(
        self, *, order_id: UUID, caller_user_id: UUID
    ) -> OrderDetail:
        order = await self._session.get(OrderRow, order_id)
        if order is None:
            raise NotFoundError("order not found")
        await self._require_member(order.tenant_id, caller_user_id)
        line_rows = (
            await self._session.execute(
                select(OrderLineRow, ProductRow, VendorProfileRow)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .join(VendorProfileRow, VendorProfileRow.id == ProductRow.vendor_id)
                .where(OrderLineRow.order_id == order.id)
                .order_by(OrderLineRow.id.asc())
            )
        ).all()
        fulfilments = {
            row.vendor_id: row
            for row in (
                await self._session.execute(
                    select(VendorFulfilmentRow).where(VendorFulfilmentRow.order_id == order.id)
                )
            ).scalars().all()
        }
        flat_lines: list[OrderLineView] = []
        by_vendor: dict[UUID, OrderVendorSlice] = {}
        for line, product, vendor in line_rows:
            view = OrderLineView(
                line_id=line.id,
                offering_id=line.offering_id,
                product_name=line.product_name,
                plan_name=line.plan_name,
                quantity=line.quantity,
                fulfilment_type=line.fulfilment_type,
                billing_period=line.billing_period,
                unit_price=float(line.unit_price),
                status=line.status,
                vendor_id=vendor.id,
                vendor_name=vendor.legal_name,
                currency=getattr(line, "currency", None) or "INR",
            )
            flat_lines.append(view)
            slice_view = by_vendor.get(vendor.id)
            if slice_view is None:
                fulfilment = fulfilments.get(vendor.id)
                by_vendor[vendor.id] = OrderVendorSlice(
                    vendor_id=vendor.id,
                    vendor_name=vendor.legal_name,
                    status=fulfilment.status if fulfilment is not None else "placed",
                    courier=fulfilment.courier if fulfilment is not None else "",
                    tracking_number=fulfilment.tracking_number if fulfilment is not None else "",
                    refund_status=fulfilment.refund_status if fulfilment is not None else "none",
                    refund_amount=(
                        float(fulfilment.refund_amount)
                        if fulfilment is not None and fulfilment.refund_amount is not None
                        else None
                    ),
                    lines=[view],
                )
            else:
                slice_view.lines.append(view)
        placed_at = order.created_at.isoformat() if order.created_at else ""
        timeline: list[TimelineStep] = [
            TimelineStep(label="Order Placed", at=placed_at, done=True),
            TimelineStep(label="Payment Confirmed", at=placed_at, done=True),
        ]
        if order.status == "cancelled":
            timeline.append(TimelineStep(label="Cancelled", at=placed_at, done=True))
        elif order.status == "delivered":
            timeline.append(TimelineStep(label="Delivered", at=placed_at, done=True))
        else:
            beyond_placed = any(fulfilment.status != "placed" for fulfilment in fulfilments.values())
            timeline.append(
                TimelineStep(label="Vendor Processing", at=placed_at, done=beyond_placed)
            )
        address_view: AddressView | None = None
        if order.address_id is not None:
            address_row = await self._session.get(AddressRow, order.address_id)
            if address_row is not None:
                address_view = self._address_view(address_row)
        return OrderDetail(
            order_id=order.id,
            status=order.status,
            payment_method=order.payment_method,
            address_id=order.address_id,
            placed_at=placed_at,
            lines=flat_lines,
            vendors=list(by_vendor.values()),
            address=address_view,
            timeline=timeline,
            tracking=None,
        )

    async def request_return(
        self,
        *,
        order_id: UUID,
        caller_user_id: UUID,
        line_id: UUID,
        reason: str,
        notes: str,
    ) -> ReturnView:
        order = await self._session.get(OrderRow, order_id)
        if order is None:
            raise NotFoundError("order not found")
        await self._require_member(order.tenant_id, caller_user_id)
        if order.status not in ("placed", "fulfilled", "partial", "processing", "delivered"):
            raise ValidationError("order cannot accept a return in its current status")
        line = await self._session.get(OrderLineRow, line_id)
        if line is None or line.order_id != order.id:
            raise NotFoundError("order line not found")
        reason = reason.strip()
        if not reason:
            raise ValidationError("reason is required")
        open_return = (
            await self._session.execute(
                select(ReturnRow.id).where(
                    ReturnRow.line_id == line.id,
                    ReturnRow.status == "requested",
                )
            )
        ).scalar_one_or_none()
        if open_return is not None:
            raise ConflictError("a return is already open for this line")
        row = ReturnRow(
            id=uuid.uuid4(),
            order_id=order.id,
            line_id=line.id,
            reason=reason,
            notes=notes.strip(),
            status="requested",
        )
        self._session.add(row)
        await audit(
            self._session,
            action="return.requested",
            actor_user_id=caller_user_id,
            tenant_id=order.tenant_id,
            payload={"return_id": str(row.id), "order_id": str(order.id), "line_id": str(line.id)},
        )
        await self._session.commit()
        return ReturnView(
            return_id=row.id,
            order_id=order.id,
            line_id=line.id,
            product_name=line.product_name,
            reason=row.reason,
            status=row.status,
        )

    async def list_returns(self, *, tenant_id: UUID, caller_user_id: UUID) -> list[ReturnView]:
        await self._require_member(tenant_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(ReturnRow, OrderLineRow)
                .join(OrderRow, OrderRow.id == ReturnRow.order_id)
                .join(OrderLineRow, OrderLineRow.id == ReturnRow.line_id)
                .where(OrderRow.tenant_id == tenant_id)
                .order_by(ReturnRow.created_at.desc())
            )
        ).all()
        return [
            ReturnView(
                return_id=item.id,
                order_id=item.order_id,
                line_id=item.line_id,
                product_name=line.product_name,
                reason=item.reason,
                status=item.status,
            )
            for item, line in rows
        ]

    async def list_subscriptions(
        self,
        *,
        tenant_id: UUID,
        caller_principal_id: UUID,
        request_id: str | None,
    ) -> list[SubscriptionView]:
        await self._require_permission(caller_principal_id, tenant_id, "resource.read", request_id)
        items: list[SubscriptionView] = []
        installs = (
            await self._session.execute(
                select(InstallationRow, OfferingRow, ProductRow)
                .join(OfferingRow, OfferingRow.id == InstallationRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .where(
                    InstallationRow.tenant_id == tenant_id,
                    InstallationRow.status.in_(("active", "cancel_at_period_end")),
                    OfferingRow.billing_period != "one_time",
                )
            )
        ).all()
        for installation, offering, product in installs:
            items.append(
                SubscriptionView(
                    offering_id=offering.id,
                    product_name=product.name,
                    plan_name=offering.plan_name,
                    status=installation.status,
                    next_billing_at=self._next_bill(installation.created_at, offering.billing_period),
                )
            )
        order_lines = (
            await self._session.execute(
                select(OrderLineRow, OfferingRow)
                .join(OrderRow, OrderRow.id == OrderLineRow.order_id)
                .join(OfferingRow, OfferingRow.id == OrderLineRow.offering_id)
                .where(
                    OrderRow.tenant_id == tenant_id,
                    OrderLineRow.status.in_(("active", "cancel_at_period_end")),
                    OrderLineRow.billing_period != "one_time",
                )
            )
        ).all()
        seen = {item.offering_id for item in items}
        for line, offering in order_lines:
            if line.offering_id in seen:
                continue
            items.append(
                SubscriptionView(
                    offering_id=line.offering_id,
                    product_name=line.product_name,
                    plan_name=line.plan_name,
                    status=line.status,
                    next_billing_at=self._next_bill(None, offering.billing_period),
                )
            )
        return items

    async def cancel_subscription(
        self,
        *,
        tenant_id: UUID,
        caller_user_id: UUID,
        caller_principal_id: UUID,
        offering_id: UUID,
        request_id: str | None,
    ) -> SubscriptionView:
        await self._require_permission(
            caller_principal_id, tenant_id, "resource.create", request_id
        )
        installation = (
            await self._session.execute(
                select(InstallationRow).where(
                    InstallationRow.tenant_id == tenant_id,
                    InstallationRow.offering_id == offering_id,
                    InstallationRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if installation is not None:
            installation.status = "cancel_at_period_end"
            offering = await self._session.get(OfferingRow, offering_id)
            product = await self._session.get(ProductRow, offering.product_id) if offering else None
            await audit(
                self._session,
                action="subscription.cancel_scheduled",
                actor_user_id=caller_user_id,
                tenant_id=tenant_id,
                payload={"offering_id": str(offering_id), "installation_id": str(installation.id)},
            )
            await self._session.commit()
            return SubscriptionView(
                offering_id=offering_id,
                product_name=product.name if product else "",
                plan_name=offering.plan_name if offering else "",
                status=installation.status,
                next_billing_at=self._next_bill(
                    installation.created_at, offering.billing_period if offering else "monthly"
                ),
            )
        line = (
            await self._session.execute(
                select(OrderLineRow)
                .join(OrderRow, OrderRow.id == OrderLineRow.order_id)
                .where(
                    OrderRow.tenant_id == tenant_id,
                    OrderLineRow.offering_id == offering_id,
                    OrderLineRow.status == "active",
                )
            )
        ).scalar_one_or_none()
        if line is None:
            raise NotFoundError("subscription not found")
        line.status = "cancel_at_period_end"
        await audit(
            self._session,
            action="subscription.cancel_scheduled",
            actor_user_id=caller_user_id,
            tenant_id=tenant_id,
            payload={"offering_id": str(offering_id), "line_id": str(line.id)},
        )
        await self._session.commit()
        return SubscriptionView(
            offering_id=offering_id,
            product_name=line.product_name,
            plan_name=line.plan_name,
            status=line.status,
            next_billing_at=self._next_bill(None, line.billing_period),
        )

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

    async def _require_permission(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        permission: str,
        request_id: str | None,
    ) -> None:
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

    async def _published_product(self, product_id: UUID) -> ProductRow:
        product = await self._session.get(ProductRow, product_id)
        if product is None or product.status != "published":
            raise NotFoundError("product not found")
        return product

    async def _published_offering(self, offering_id: UUID) -> tuple[OfferingRow, ProductRow]:
        offering = await self._session.get(OfferingRow, offering_id)
        if offering is None or offering.status != "published":
            raise NotFoundError("offering not found")
        product = await self._session.get(ProductRow, offering.product_id)
        if product is None or product.status != "published":
            raise NotFoundError("offering not found")
        return offering, product

    async def _open_cart(self, tenant_id: UUID) -> CartRow | None:
        return (
            await self._session.execute(
                select(CartRow).where(CartRow.tenant_id == tenant_id, CartRow.status == "open")
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
                .order_by(CartLineRow.created_at.asc())
            )
        ).all()
        return [(line, offering, product) for line, offering, product in rows]

    async def _cart_lines(self, cart_id: UUID) -> list[CartLineView]:
        rows = (
            await self._session.execute(
                select(CartLineRow, OfferingRow, ProductRow, VendorProfileRow)
                .join(OfferingRow, OfferingRow.id == CartLineRow.offering_id)
                .join(ProductRow, ProductRow.id == OfferingRow.product_id)
                .join(VendorProfileRow, VendorProfileRow.id == ProductRow.vendor_id)
                .where(CartLineRow.cart_id == cart_id)
                .order_by(CartLineRow.created_at.asc())
            )
        ).all()
        return [
            CartLineView(
                line_id=line.id,
                offering_id=offering.id,
                product_id=product.id,
                product_name=product.name,
                plan_name=offering.plan_name,
                quantity=line.quantity,
                unit_price=float(offering.price_usd),
                fulfilment_type=product.fulfilment_type,
                billing_period=offering.billing_period,
                vendor_id=vendor.id,
                vendor_name=vendor.legal_name,
                currency=getattr(offering, "currency", None) or "INR",
            )
            for line, offering, product, vendor in rows
        ]

    async def _line_on_cart(self, cart: CartRow | None, line_id: UUID) -> CartLineRow:
        if cart is None:
            raise NotFoundError("cart line not found")
        line = await self._session.get(CartLineRow, line_id)
        if line is None or line.cart_id != cart.id:
            raise NotFoundError("cart line not found")
        return line

    async def _address(self, tenant_id: UUID, address_id: UUID) -> AddressRow:
        row = await self._session.get(AddressRow, address_id)
        if row is None or row.tenant_id != tenant_id or row.status != "active":
            raise NotFoundError("address not found")
        return row

    def _address_view(self, row: AddressRow) -> AddressView:
        return AddressView(
            address_id=row.id,
            label=row.label,
            contact_name=row.contact_name,
            line1=row.line1,
            city=row.city,
            state=row.state,
            pincode=row.pincode,
            phone=row.phone,
        )

    def _check_quantity(self, quantity: int) -> None:
        if quantity < 1:
            raise ValidationError("quantity must be at least 1")

    def _next_bill(self, start, billing_period: str) -> str | None:
        base = start or utcnow()
        if billing_period == "yearly":
            return (base + timedelta(days=365)).isoformat()
        if billing_period == "one_time":
            return None
        return (base + timedelta(days=30)).isoformat()
