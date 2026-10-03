"""0016 vendor account

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-03

Vendor settings, support requests, and the payout ledger read by the vendor portal.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), primary_key=True),
        sa.Column("support_email", sa.String(255), nullable=False, server_default=""),
        sa.Column("bank_account_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("bank_account_number", sa.String(64), nullable=False, server_default=""),
        sa.Column("bank_ifsc", sa.String(16), nullable=False, server_default=""),
        sa.Column("notify_install", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notify_payout", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="vendor",
    )
    op.create_table(
        "support_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="vendor",
    )
    op.create_index("ix_support_requests_vendor_id", "support_requests", ["vendor_id"], schema="vendor")
    op.create_table(
        "payouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("gross", sa.Numeric(12, 2), nullable=False),
        sa.Column("platform_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("net", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("vendor_id", "period", name="uq_payouts_vendor_period"),
        schema="marketplace",
    )
    op.create_index("ix_payouts_vendor_id", "payouts", ["vendor_id"], schema="marketplace")


def downgrade() -> None:
    op.drop_index("ix_payouts_vendor_id", table_name="payouts", schema="marketplace")
    op.drop_table("payouts", schema="marketplace")
    op.drop_index("ix_support_requests_vendor_id", table_name="support_requests", schema="vendor")
    op.drop_table("support_requests", schema="vendor")
    op.drop_table("settings", schema="vendor")
