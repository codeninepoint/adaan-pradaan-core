"""0021 platform admin remaining nine

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-17

product.pa_status, platform_policies, platform_config, platform_team_members,
and platform.audit.read permission.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")

    op.add_column(
        "products",
        sa.Column("pa_status", sa.String(32), nullable=False, server_default="not_submitted"),
        schema="marketplace",
    )
    op.add_column(
        "products",
        sa.Column("pa_reject_reason", sa.Text(), nullable=False, server_default=""),
        schema="marketplace",
    )
    op.create_index("ix_products_pa_status", "products", ["pa_status"], schema="marketplace")
    op.execute(
        """
        UPDATE marketplace.products
        SET pa_status = 'live'
        WHERE status = 'published'
        """
    )

    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("enforcement", sa.String(64), nullable=False, server_default="mandatory"),
        sa.Column("applies_to", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="enforced"),
        sa.Column(
            "body",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="platform",
    )

    op.create_table(
        "config",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        schema="platform",
    )

    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id"),
            nullable=True,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("platform_role", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="invited"),
        sa.Column("invited_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("invite_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email", name="uq_platform_team_members_email"),
        schema="platform",
    )
    op.create_index("ix_platform_team_members_user_id", "team_members", ["user_id"], schema="platform")

    op.execute(
        """
        INSERT INTO platform.config (key, value) VALUES
          ('platform_name', '"AdanPradan FairShare"'::jsonb),
          ('commission_rate_pct', '10'::jsonb),
          ('settlement_cycle', '"weekly_t7"'::jsonb),
          ('plugin_review_sla_days', '3'::jsonb),
          ('webhook_hmac_key', '""'::jsonb),
          ('product_content_review_required', 'true'::jsonb)
        ON CONFLICT (key) DO NOTHING
        """
    )

    # Seed default policies
    op.execute(
        """
        INSERT INTO platform.policies (id, name, scope, enforcement, applies_to, status, body)
        VALUES
          (gen_random_uuid(), 'HMAC-SHA256 Webhook Signing', 'plugins', 'mandatory', 'All plugins', 'enforced', '{}'),
          (gen_random_uuid(), 'KYC before vendor activation', 'vendors', 'mandatory', 'All vendors', 'enforced', '{}'),
          (gen_random_uuid(), 'Capability declaration required', 'plugins', 'mandatory', 'All plugins', 'enforced', '{}'),
          (gen_random_uuid(), 'Semantic versioning (semver)', 'plugins', 'validation', 'All plugins', 'enforced', '{}'),
          (gen_random_uuid(), 'Tenant isolation — no cross-tenant data', 'data', 'system', 'All tenants', 'enforced', '{}'),
          (gen_random_uuid(), 'Location match required for checkout', 'products', 'automatic', 'All customers', 'enforced', '{}'),
          (gen_random_uuid(), 'Service account: API key rotation 90d', 'accounts', 'mandatory', 'Service accounts', 'enforced', '{}'),
          (gen_random_uuid(), 'MFA mandatory for Tenant Admin+', 'auth', 'mandatory', 'Admin roles', 'enforced', '{}')
        """
    )

    op.execute(
        """
        INSERT INTO authz.permissions (id, code, scope_type, description, status)
        VALUES (gen_random_uuid(), 'platform.audit.read', 'platform', 'Read cross-tenant audit log', 'active')
        ON CONFLICT (code) DO UPDATE SET status = 'active'
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM authz.permissions WHERE code = 'platform.audit.read'")
    op.drop_index("ix_platform_team_members_user_id", table_name="team_members", schema="platform")
    op.drop_table("team_members", schema="platform")
    op.drop_table("config", schema="platform")
    op.drop_table("policies", schema="platform")
    op.drop_index("ix_products_pa_status", table_name="products", schema="marketplace")
    op.drop_column("products", "pa_reject_reason", schema="marketplace")
    op.drop_column("products", "pa_status", schema="marketplace")
    op.execute("DROP SCHEMA IF EXISTS platform CASCADE")
