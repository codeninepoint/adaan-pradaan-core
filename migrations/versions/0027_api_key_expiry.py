"""0027 api key expiry

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-17

identity.api_keys: expires_at + last_used_at (90-day rotation policy)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        schema="identity",
    )
    op.add_column(
        "api_keys",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        schema="identity",
    )
    op.execute(
        """
        UPDATE identity.api_keys
        SET expires_at = created_at + interval '90 days'
        WHERE expires_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("api_keys", "last_used_at", schema="identity")
    op.drop_column("api_keys", "expires_at", schema="identity")
