from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.infrastructure.models import Base, TimestampMixin


class VendorProfileRow(Base, TimestampMixin):
    __tablename__ = "profiles"
    __table_args__ = {"schema": "vendor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.organizations.id"), unique=True, index=True
    )
    legal_name: Mapped[str] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payout_bank_account: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(255))
    business_doc_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending_verification")


class VendorVerificationRow(Base):
    __tablename__ = "verifications"
    __table_args__ = {"schema": "vendor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class VendorSettingsRow(Base):
    __tablename__ = "settings"
    __table_args__ = {"schema": "vendor"}

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), primary_key=True
    )
    support_email: Mapped[str] = mapped_column(String(255), default="")
    bank_account_name: Mapped[str] = mapped_column(String(255), default="")
    bank_account_number: Mapped[str] = mapped_column(String(64), default="")
    bank_ifsc: Mapped[str] = mapped_column(String(16), default="")
    notify_install: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_payout: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SupportRequestRow(Base):
    __tablename__ = "support_requests"
    __table_args__ = {"schema": "vendor"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendor.profiles.id"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
