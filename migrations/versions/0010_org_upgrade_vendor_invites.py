"""0010 org upgrade vendor invites

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-23

- organization_registration_requests for J07
- vendor schema (profiles + verifications) for J20–J22
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_registration_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.organizations.id"), nullable=False),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("country", sa.String(8), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="processing"),
        sa.Column("keycloak_realm_ref", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="tenant",
    )
    op.create_index(
        "ix_org_reg_requests_requester",
        "organization_registration_requests",
        ["requester_user_id"],
        schema="tenant",
    )
    op.create_index(
        "ix_org_reg_requests_slug",
        "organization_registration_requests",
        ["slug"],
        schema="tenant",
    )

    op.execute("CREATE SCHEMA IF NOT EXISTS vendor")
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.organizations.id"), nullable=False, unique=True),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("tax_id", sa.String(128), nullable=True),
        sa.Column("payout_bank_account", sa.String(255), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("business_doc_url", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending_verification"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="vendor",
    )
    op.create_table(
        "verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vendor.profiles.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="vendor",
    )


def downgrade() -> None:
    op.drop_table("verifications", schema="vendor")
    op.drop_table("profiles", schema="vendor")
    op.execute("DROP SCHEMA IF EXISTS vendor")
    op.drop_index("ix_org_reg_requests_slug", table_name="organization_registration_requests", schema="tenant")
    op.drop_index("ix_org_reg_requests_requester", table_name="organization_registration_requests", schema="tenant")
    op.drop_table("organization_registration_requests", schema="tenant")
