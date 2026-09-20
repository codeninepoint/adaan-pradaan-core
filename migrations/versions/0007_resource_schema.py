"""0007 resource schema

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS resource")
    op.create_table(
        "resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("resource_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("external_ref", sa.String(512), nullable=True),
        sa.Column("created_by_principal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'provisioning', 'suspended', 'deleted')",
            name="ck_resources_status",
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_resources_tenant_name"),
        schema="resource",
    )
    op.create_index("ix_resources_tenant_id", "resources", ["tenant_id"], schema="resource")
    op.create_index(
        "ix_resources_tenant_type",
        "resources",
        ["tenant_id", "resource_type"],
        schema="resource",
    )


def downgrade() -> None:
    op.drop_index("ix_resources_tenant_type", table_name="resources", schema="resource")
    op.drop_index("ix_resources_tenant_id", table_name="resources", schema="resource")
    op.drop_table("resources", schema="resource")
    op.execute("DROP SCHEMA IF EXISTS resource CASCADE")
