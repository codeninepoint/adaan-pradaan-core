"""0024 currency INR default

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-17

offerings/order_lines/settings/city currency columns + backfill
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "offerings",
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        schema="marketplace",
    )
    op.add_column(
        "order_lines",
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        schema="marketplace",
    )
    op.add_column(
        "settings",
        sa.Column("default_currency", sa.String(3), nullable=False, server_default="INR"),
        schema="vendor",
    )
    op.add_column(
        "vendor_service_cities",
        sa.Column("currency", sa.String(3), nullable=True),
        schema="marketplace",
    )

    # Physical listings with mrp_inr in content stay INR (already default).
    # Software offerings without mrp payload → USD.
    op.execute(
        """
        UPDATE marketplace.offerings o
        SET currency = 'USD'
        WHERE NOT EXISTS (
          SELECT 1
          FROM marketplace.product_content pc
          WHERE pc.product_id = o.product_id
            AND (pc.payload ? 'mrp_inr' OR pc.payload ? 'mrp_amount')
        )
        AND o.billing_period IS DISTINCT FROM 'one_time'
        """
    )


def downgrade() -> None:
    op.drop_column("vendor_service_cities", "currency", schema="marketplace")
    op.drop_column("settings", "default_currency", schema="vendor")
    op.drop_column("order_lines", "currency", schema="marketplace")
    op.drop_column("offerings", "currency", schema="marketplace")
