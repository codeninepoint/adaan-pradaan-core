"""0011 credential password hash

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27

Store a local password hash so login can restore a Keycloak user after the
IdP process loses its in-memory or unpersisted accounts.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credentials",
        sa.Column("password_hash", sa.String(255), nullable=True),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("credentials", "password_hash", schema="identity")
