"""0032 press releases

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-22

Publicity standard plugin: per-vendor press releases written and
distributed from the vendor Publicity page.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "press_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("headline", sa.String(512), nullable=False, server_default=""),
        sa.Column("template", sa.String(64), nullable=False, server_default="product-launch"),
        sa.Column("distribution", sa.String(64), nullable=False, server_default="media-contacts"),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendor.profiles.id"]),
        schema="marketplace",
    )
    op.create_index("ix_press_releases_vendor_id", "press_releases", ["vendor_id"], schema="marketplace")


def downgrade() -> None:
    op.drop_table("press_releases", schema="marketplace")
