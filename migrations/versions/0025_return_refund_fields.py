"""0025 return refund fields

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-17

returns: refund amount/method/currency + vendor decision timestamps
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "returns",
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        schema="marketplace",
    )
    op.add_column(
        "returns",
        sa.Column("refund_currency", sa.String(3), nullable=False, server_default="INR"),
        schema="marketplace",
    )
    op.add_column(
        "returns",
        sa.Column("refund_method", sa.String(32), nullable=True),
        schema="marketplace",
    )
    op.add_column(
        "returns",
        sa.Column("vendor_notes", sa.Text(), nullable=False, server_default=""),
        schema="marketplace",
    )
    op.add_column(
        "returns",
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        schema="marketplace",
    )
    op.add_column(
        "returns",
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_column("returns", "refunded_at", schema="marketplace")
    op.drop_column("returns", "decided_at", schema="marketplace")
    op.drop_column("returns", "vendor_notes", schema="marketplace")
    op.drop_column("returns", "refund_method", schema="marketplace")
    op.drop_column("returns", "refund_currency", schema="marketplace")
    op.drop_column("returns", "refund_amount", schema="marketplace")
