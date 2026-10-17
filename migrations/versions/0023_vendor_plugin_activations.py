"""0023 vendor plugin activations

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-17

vendor_plugin_activations for platform standard plugin activate/deactivate.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_plugin_activations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendor.profiles.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "plugin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("marketplace.plugins.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("activated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("vendor_id", "plugin_id", name="uq_vendor_plugin_activations_vendor_plugin"),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_table("vendor_plugin_activations", schema="marketplace")
