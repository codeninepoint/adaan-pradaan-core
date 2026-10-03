from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
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
    ProductRow,
    ReturnRow,
    VendorFulfilmentRow,
    WishlistRow,
)
from shared.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from tenant.infrastructure.models import AddressRow, TenantMembershipRow, TenantRow
from vendor.infrastructure.models import VendorProfileRow

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
class OrderSummary:
    order_id: UUID
    status: str
    payment_method: str
    placed_at: str
    line_count: int
    total: float


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


FULFILMENT_TRANSITIONS: dict[str, frozenset[str]] = {
    "placed": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"processing"}),
    "processing": frozenset({"ready_to_ship"}),
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


@dataclass(frozen=True, slots=True)
class PayoutView:
    period: str
    gross: float
    platform_fee: float
    net: float
    status: str


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


@dataclass(frozen=True, slots=True)
class OrderDetail:
    order_id: UUID
    status: str
    payment_method: str
    address_id: UUID | None
    placed_at: str
    lines: list[OrderLineView]
    tracking: None


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
                    status="active",
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
            summaries.append(
                OrderSummary(
                    order_id=order.id,
                    status=order.status,
                    payment_method=order.payment_method,
                    placed_at=order.created_at.isoformat() if order.created_at else "",
                    line_count=len(lines),
                    total=total,
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
            )
            self._session.add(current)
        else:
            current.status = status
            if status == "shipped":
                current.courier = cleaned_courier
                current.tracking_number = cleaned_tracking
            current.updated_at = utcnow()
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
        await self._session.commit()
        return current

    async def list_vendor_customers(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[VendorCustomer]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
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
            if bucket is None:
                grouped[tenant.id] = {
                    "name": name,
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
        customers = [
            VendorCustomer(
                tenant_id=tenant_id,
                customer_name=bucket["name"],
                order_count=len(bucket["orders"]),
                total=bucket["total"],
                last_order_at=bucket["last"],
            )
            for tenant_id, bucket in grouped.items()
        ]
        customers.sort(key=lambda item: item.last_order_at, reverse=True)
        return customers

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
            )
            for item, line, _order, tenant, address in rows
        ]

    async def list_vendor_payouts(
        self, *, vendor_id: UUID, caller_user_id: UUID
    ) -> list[PayoutView]:
        await require_vendor_owner(self._session, vendor_id, caller_user_id)
        rows = (
            await self._session.execute(
                select(PayoutLedgerRow)
                .where(PayoutLedgerRow.vendor_id == vendor_id)
                .order_by(PayoutLedgerRow.period.desc())
            )
        ).scalars().all()
        return [
            PayoutView(
                period=row.period,
                gross=float(row.gross),
                platform_fee=float(row.platform_fee),
                net=float(row.net),
                status=row.status,
            )
            for row in rows
        ]

    async def order_detail(
        self, *, order_id: UUID, caller_user_id: UUID
    ) -> OrderDetail:
        order = await self._session.get(OrderRow, order_id)
        if order is None:
            raise NotFoundError("order not found")
        await self._require_member(order.tenant_id, caller_user_id)
        lines = (
            await self._session.execute(
                select(OrderLineRow).where(OrderLineRow.order_id == order.id)
            )
        ).scalars().all()
        return OrderDetail(
            order_id=order.id,
            status=order.status,
            payment_method=order.payment_method,
            address_id=order.address_id,
            placed_at=order.created_at.isoformat() if order.created_at else "",
            tracking=None,
            lines=[
                OrderLineView(
                    line_id=line.id,
                    offering_id=line.offering_id,
                    product_name=line.product_name,
                    plan_name=line.plan_name,
                    quantity=line.quantity,
                    fulfilment_type=line.fulfilment_type,
                    billing_period=line.billing_period,
                    unit_price=float(line.unit_price),
                    status=line.status,
                )
                for line in lines
            ],
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
        if order.status not in ("placed", "fulfilled"):
            raise ValidationError("order is not placed or fulfilled")
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
            )
            for line, offering, product in await self._cart_line_rows(cart_id)
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
