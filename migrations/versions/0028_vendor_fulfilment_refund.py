"""0028 vendor fulfilment refund fields

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-18

vendor_fulfilments: refund_status + refund_amount for reject/cancel slices
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "vendor_fulfilments",
        sa.Column("refund_status", sa.String(32), nullable=False, server_default="none"),
        schema="marketplace",
    )
    op.add_column(
        "vendor_fulfilments",
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_column("vendor_fulfilments", "refund_amount", schema="marketplace")
    op.drop_column("vendor_fulfilments", "refund_status", schema="marketplace")
