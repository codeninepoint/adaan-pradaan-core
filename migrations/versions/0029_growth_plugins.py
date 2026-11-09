"""0029 growth plugins

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-21

Platform Admin Sales & Growth standard plugins (Sales Pipeline, Digital
Marketing, Publicity) with module toggles and configuration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "growth_plugins",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("group_label", sa.String(32), nullable=False, server_default=""),
        sa.Column("lifecycle", sa.String(16), nullable=False, server_default="live"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("modules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("stats", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("guarantees", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_table("growth_plugins", schema="marketplace")
