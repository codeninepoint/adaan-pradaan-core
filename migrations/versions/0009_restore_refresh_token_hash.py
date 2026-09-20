"""0009 restore session refresh token hash

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-15

Restores identity.sessions.refresh_token_hash for platform-issued
refresh rotation (multi-tenant auth). Access JWTs remain lean (no roles).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("refresh_token_hash", sa.String(255), nullable=True),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("sessions", "refresh_token_hash", schema="identity")
