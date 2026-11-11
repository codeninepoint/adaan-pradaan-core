"""0038 payment intents

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-11

Cashfree Payment Gateway: payment intents, webhook events, and refunds
linked to marketplace orders.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.orders.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("provider", sa.String(32), nullable=False, server_default="cashfree"),
        sa.Column("merchant_order_id", sa.String(64), nullable=False),
        sa.Column("cf_order_id", sa.String(64), nullable=True),
        sa.Column("payment_session_id", sa.String(512), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(32), nullable=False, server_default="created"),
        sa.Column("payment_method", sa.String(32), nullable=False, server_default=""),
        sa.Column("cf_payment_id", sa.String(64), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider", "merchant_order_id", name="uq_payment_intents_provider_merchant"
        ),
        schema="marketplace",
    )
    op.create_table(
        "payment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_intent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.payment_intents.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("provider", sa.String(32), nullable=False, server_default="cashfree"),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("signature_ok", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="marketplace",
    )
    op.create_index(
        "ix_payment_events_idempotency",
        "payment_events",
        ["provider", "idempotency_key"],
        unique=False,
        schema="marketplace",
    )
    op.create_table(
        "payment_refunds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_intent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.payment_intents.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.orders.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("return_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("cf_refund_id", sa.String(64), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(255), nullable=False, server_default=""),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_table("payment_refunds", schema="marketplace")
    op.drop_index(
        "ix_payment_events_idempotency", table_name="payment_events", schema="marketplace"
    )
    op.drop_table("payment_events", schema="marketplace")
    op.drop_table("payment_intents", schema="marketplace")
