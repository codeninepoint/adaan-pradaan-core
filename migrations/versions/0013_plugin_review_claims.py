"""0013 plugin review claims

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-02

Claim and reviewer notes for plugin governance (J26, J35).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "plugin_versions",
        sa.Column("claimed_by", postgresql.UUID(as_uuid=True), nullable=True),
        schema="marketplace",
    )
    op.add_column(
        "plugin_versions",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        schema="marketplace",
    )
    op.add_column(
        "plugin_versions",
        sa.Column("review_notes", sa.Text(), nullable=False, server_default=""),
        schema="marketplace",
    )


def downgrade() -> None:
    op.drop_column("plugin_versions", "review_notes", schema="marketplace")
    op.drop_column("plugin_versions", "claimed_at", schema="marketplace")
    op.drop_column("plugin_versions", "claimed_by", schema="marketplace")
