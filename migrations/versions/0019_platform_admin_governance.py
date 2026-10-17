"""0019 platform admin governance

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-17

Standard plugins (owner_kind, nullable vendor_id, requirements) and
plugin version risk_level for governance filters.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plugins",
        sa.Column("owner_kind", sa.String(32), nullable=False, server_default="vendor"),
        schema="marketplace",
    )
    op.add_column(
        "plugins",
        sa.Column(
            "requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema="marketplace",
    )
    op.alter_column(
        "plugins",
        "vendor_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        schema="marketplace",
    )
    op.create_index(
        "ix_plugins_owner_kind_category",
        "plugins",
        ["owner_kind", "category"],
        unique=False,
        schema="marketplace",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_plugins_platform_category
        ON marketplace.plugins (category)
        WHERE owner_kind = 'platform'
        """
    )

    op.add_column(
        "plugin_versions",
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        schema="marketplace",
    )
    op.create_index(
        "ix_plugin_versions_risk_level",
        "plugin_versions",
        ["risk_level"],
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_index("ix_plugin_versions_risk_level", table_name="plugin_versions", schema="marketplace")
    op.drop_column("plugin_versions", "risk_level", schema="marketplace")
    op.execute("DROP INDEX IF EXISTS marketplace.uq_plugins_platform_category")
    op.drop_index("ix_plugins_owner_kind_category", table_name="plugins", schema="marketplace")
    op.alter_column(
        "plugins",
        "vendor_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        schema="marketplace",
    )
    op.drop_column("plugins", "requirements", schema="marketplace")
    op.drop_column("plugins", "owner_kind", schema="marketplace")
