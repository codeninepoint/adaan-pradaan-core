"""0035 settlement hub

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-10

Platform Admin Settlement: IMPS batches, contested returns, vendor ledger,
TDS/GST, escrow window orders, platform faults, and fraud signals.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "settlement_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_time", sa.String(16), nullable=False),
        sa.Column("vendors", sa.Integer(), nullable=True),
        sa.Column("orders", sa.Integer(), nullable=True),
        sa.Column("gross", sa.Numeric(12, 2), nullable=True),
        sa.Column("deductions", sa.Numeric(12, 2), nullable=True),
        sa.Column("net", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(64), nullable=False, server_default="done"),
        sa.Column("utr", sa.String(128), nullable=True),
        sa.Column("batch_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "settlement_return_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("case_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(64), nullable=False, server_default="open"),
        sa.Column("customer_claim", sa.Text(), nullable=False, server_default=""),
        sa.Column("vendor_claim", sa.Text(), nullable=False, server_default=""),
        sa.Column("reason_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("amount_at_stake", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("timeline", sa.Text(), nullable=False, server_default=""),
        sa.Column("deadline_seconds", sa.Integer(), nullable=True),
        sa.Column("chat", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="platform",
    )

    op.create_table(
        "settlement_ledger_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_name", sa.String(255), nullable=False, index=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("order_time", sa.String(16), nullable=False, server_default=""),
        sa.Column("items", sa.String(512), nullable=False, server_default=""),
        sa.Column("gross", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deductions", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(64), nullable=False, server_default="settled"),
        sa.Column("utr", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "settlement_tds_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("period", sa.String(32), nullable=False, server_default="Oct 2026"),
        sa.Column("gross_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tds_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "settlement_escrow_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("delivered_at", sa.String(16), nullable=False, server_default=""),
        sa.Column("window_closes_at", sa.String(16), nullable=False, server_default=""),
        sa.Column("minutes_left", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(64), nullable=False, server_default="window_open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "settlement_faults",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_ref", sa.String(32), nullable=False),
        sa.Column("fault_type", sa.String(128), nullable=False),
        sa.Column("customer_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("resolved_in", sa.String(32), nullable=False, server_default=""),
        sa.Column("vendor_impact", sa.String(64), nullable=False, server_default="not_touched"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )

    op.create_table(
        "settlement_fraud_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("party_name", sa.String(255), nullable=False),
        sa.Column("party_type", sa.String(32), nullable=False),
        sa.Column("signal", sa.Text(), nullable=False, server_default=""),
        sa.Column("returns_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("action_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("settlement_fraud_signals", schema="platform")
    op.drop_table("settlement_faults", schema="platform")
    op.drop_table("settlement_escrow_orders", schema="platform")
    op.drop_table("settlement_tds_rows", schema="platform")
    op.drop_table("settlement_ledger_lines", schema="platform")
    op.drop_table("settlement_return_cases", schema="platform")
    op.drop_table("settlement_batches", schema="platform")
