from __future__ import annotations

import uuid
from datetime import datetime

from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models import Base, TimestampMixin


class PlatformPolicyRow(Base, TimestampMixin):
    __tablename__ = "policies"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(64))
    enforcement: Mapped[str] = mapped_column(String(64), default="mandatory")
    applies_to: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="enforced")
    body: Mapped[dict] = mapped_column(JSONB, default=dict)


class PlatformConfigRow(Base):
    __tablename__ = "config"
    __table_args__ = {"schema": "platform"}

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[object] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class PlatformTeamMemberRow(Base, TimestampMixin):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("email", name="uq_platform_team_members_email"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255))
    platform_role: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="invited")
    invited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    invite_note: Mapped[str] = mapped_column(Text, default="")


class CommunicationTemplateRow(Base, TimestampMixin):
    __tablename__ = "communication_templates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_communication_templates_code"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    channel: Mapped[str] = mapped_column(String(16), index=True)
    plugin: Mapped[str] = mapped_column(String(64), default="Sales")
    message_type: Mapped[str] = mapped_column(String(64), default="Marketing")
    body: Mapped[str] = mapped_column(Text, default="")
    approval_status: Mapped[str] = mapped_column(String(64), default="draft", index=True)
    dlt_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendors_using: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent_month: Mapped[int] = mapped_column(Integer, default=0)
    variable_map: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunicationUsageLogRow(Base):
    __tablename__ = "communication_usage_logs"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), default="")
    channel: Mapped[str] = mapped_column(String(16))
    template_code: Mapped[str] = mapped_column(String(64), default="")
    template_name: Mapped[str] = mapped_column(String(255), default="")
    audience: Mapped[str] = mapped_column(String(255), default="")
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    delivered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    replied_count: Mapped[int] = mapped_column(Integer, default=0)
    variables: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(64), default="done")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CommunicationTemplateRequestRow(Base):
    __tablename__ = "communication_template_requests"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), default="")
    channel: Mapped[str] = mapped_column(String(16), default="sms")
    name: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CommunicationOptoutRow(Base):
    __tablename__ = "communication_optouts"
    __table_args__ = (
        UniqueConstraint("channel", "contact_ref", name="uq_communication_optouts_channel_contact"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(16), index=True)
    contact_ref: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(String(128), default="user_request")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SettlementBatchRow(Base):
    __tablename__ = "settlement_batches"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_time: Mapped[str] = mapped_column(String(16))
    vendors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orders: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    deductions: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    net: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="done")
    utr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    batch_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SettlementReturnCaseRow(Base):
    __tablename__ = "settlement_return_cases"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_ref: Mapped[str] = mapped_column(String(32))
    vendor_name: Mapped[str] = mapped_column(String(255), default="")
    case_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(64), default="open")
    customer_claim: Mapped[str] = mapped_column(Text, default="")
    vendor_claim: Mapped[str] = mapped_column(Text, default="")
    reason_code: Mapped[str] = mapped_column(String(64), default="")
    amount_at_stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    timeline: Mapped[str] = mapped_column(Text, default="")
    deadline_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chat: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SettlementLedgerLineRow(Base):
    __tablename__ = "settlement_ledger_lines"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_name: Mapped[str] = mapped_column(String(255), index=True)
    order_ref: Mapped[str] = mapped_column(String(32))
    order_time: Mapped[str] = mapped_column(String(16), default="")
    items: Mapped[str] = mapped_column(String(512), default="")
    gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    net_label: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(64), default="settled")
    utr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SettlementTdsRow(Base):
    __tablename__ = "settlement_tds_rows"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_name: Mapped[str] = mapped_column(String(255))
    period: Mapped[str] = mapped_column(String(32), default="Oct 2026")
    gross_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    tds_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    net_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SettlementEscrowOrderRow(Base):
    __tablename__ = "settlement_escrow_orders"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_ref: Mapped[str] = mapped_column(String(32))
    vendor_name: Mapped[str] = mapped_column(String(255))
    delivered_at: Mapped[str] = mapped_column(String(16), default="")
    window_closes_at: Mapped[str] = mapped_column(String(16), default="")
    minutes_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(64), default="window_open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SettlementFaultRow(Base):
    __tablename__ = "settlement_faults"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_ref: Mapped[str] = mapped_column(String(32))
    fault_type: Mapped[str] = mapped_column(String(128))
    customer_name: Mapped[str] = mapped_column(String(128), default="")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    resolved_in: Mapped[str] = mapped_column(String(32), default="")
    vendor_impact: Mapped[str] = mapped_column(String(64), default="not_touched")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SettlementFraudSignalRow(Base):
    __tablename__ = "settlement_fraud_signals"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    party_name: Mapped[str] = mapped_column(String(255))
    party_type: Mapped[str] = mapped_column(String(32))
    signal: Mapped[str] = mapped_column(Text, default="")
    returns_label: Mapped[str] = mapped_column(String(64), default="")
    action_label: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VendorSettlementOrderRow(Base):
    __tablename__ = "vendor_settlement_orders"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    order_ref: Mapped[str] = mapped_column(String(32))
    order_time: Mapped[str] = mapped_column(String(16), default="")
    items: Mapped[str] = mapped_column(String(512), default="")
    gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    net: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(64), default="window_open")
    window_label: Mapped[str] = mapped_column(String(64), default="")
    settlement_label: Mapped[str] = mapped_column(String(64), default="")
    return_label: Mapped[str] = mapped_column(String(64), default="")
    in_tracker: Mapped[bool] = mapped_column(Boolean, default=False)
    in_today: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VendorSettlementReturnRow(Base):
    __tablename__ = "vendor_settlement_returns"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    order_ref: Mapped[str] = mapped_column(String(32))
    customer_name: Mapped[str] = mapped_column(String(128), default="")
    complaint: Mapped[str] = mapped_column(Text, default="")
    reason_code: Mapped[str] = mapped_column(String(64), default="")
    refund_requested: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    amount_on_hold: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    order_items: Mapped[str] = mapped_column(Text, default="")
    timeline: Mapped[str] = mapped_column(Text, default="")
    deadline_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="open")
    contest_reason: Mapped[str] = mapped_column(Text, default="")
    chat: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VendorSettlementHistoryRow(Base):
    __tablename__ = "vendor_settlement_history"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    settle_date: Mapped[str] = mapped_column(String(32))
    orders: Mapped[int] = mapped_column(Integer, default=0)
    gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    deductions: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    refund_adj: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    net: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    utr: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VendorSettlementBankRow(Base):
    __tablename__ = "vendor_settlement_bank"
    __table_args__ = (
        UniqueConstraint("vendor_id", name="uq_vendor_settlement_bank_vendor"),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    bank_name: Mapped[str] = mapped_column(String(255), default="")
    account_mask: Mapped[str] = mapped_column(String(64), default="")
    ifsc: Mapped[str] = mapped_column(String(32), default="")
    branch: Mapped[str] = mapped_column(String(128), default="")
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CustomerHubOrderRow(Base):
    __tablename__ = "customer_hub_orders"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    order_ref: Mapped[str] = mapped_column(String(32))
    vendor_name: Mapped[str] = mapped_column(String(255), default="")
    zone: Mapped[str] = mapped_column(String(128), default="")
    placed_label: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(64), default="return_window")
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    summary: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    window_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    window_closes_label: Mapped[str] = mapped_column(String(32), default="")
    timeline: Mapped[list] = mapped_column(JSONB, default=list)
    bill_lines: Mapped[list] = mapped_column(JSONB, default=list)
    chat: Mapped[list] = mapped_column(JSONB, default=list)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CustomerHubReturnRow(Base):
    __tablename__ = "customer_hub_returns"
    __table_args__ = {"schema": "platform"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    order_ref: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    photo_name: Mapped[str] = mapped_column(String(255), default="")
    amount_at_stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(64), default="submitted")
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    refund_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refund_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vendor_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
