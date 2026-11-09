"""0031 marketing campaigns

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-22

Digital Marketing standard plugin: per-vendor ad campaigns shown on the
vendor Digital Marketing dashboard.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(128), nullable=False, server_default=""),
        sa.Column("spend_inr", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("ctr_percent", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.profiles.id"]),
        schema="marketplace",
    )
    op.create_index("ix_marketing_campaigns_vendor_id", "marketing_campaigns", ["vendor_id"], schema="marketplace")


def downgrade() -> None:
    op.drop_table("marketing_campaigns", schema="marketplace")
