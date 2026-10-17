from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
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
