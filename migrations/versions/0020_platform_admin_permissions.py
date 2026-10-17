"""0020 platform admin permissions

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-17

Seed new platform.* permissions used by Platform Admin governance and users.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PERMISSIONS = (
    ("platform.plugin.review", "platform", "Review and decide vendor plugin versions"),
    (
        "platform.plugin.manage_standard",
        "platform",
        "Create and lifecycle platform standard plugins",
    ),
    ("platform.user.manage", "platform", "Manage platform user directory lifecycle"),
)


def upgrade() -> None:
    connection = op.get_bind()
    for code, scope_type, description in PERMISSIONS:
        connection.execute(
            text(
                """
                INSERT INTO authz.permissions (id, code, scope_type, description, status)
                VALUES (gen_random_uuid(), :code, :scope_type, :description, 'active')
                ON CONFLICT (code) DO UPDATE SET
                  scope_type = EXCLUDED.scope_type,
                  description = COALESCE(EXCLUDED.description, authz.permissions.description),
                  status = 'active'
                """
            ),
            {"code": code, "scope_type": scope_type, "description": description},
        )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM authz.permissions
        WHERE code IN (
          'platform.plugin.review',
          'platform.plugin.manage_standard',
          'platform.user.manage'
        )
        """
    )
