"""0017 warehouse capacity

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-03

Unit capacity the vendor sets for each warehouse.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "warehouses",
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="0"),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_column("warehouses", "capacity", schema="marketplace")
