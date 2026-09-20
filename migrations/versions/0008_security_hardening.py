"""0008 security hardening constraints

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-07

- delivery_secrets for one-time plaintext (outbox never stores secrets long-term)
- membership FKs + unique indexes
- principal_roles scope-match trigger
- resources.created_by_principal_id FK
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "delivery_secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("secret_plain", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "purpose IN ('verification_email', 'password_reset_email')",
            name="ck_delivery_secrets_purpose",
        ),
        schema="identity",
    )
    op.create_index(
        "ix_delivery_secrets_purpose_created",
        "delivery_secrets",
        ["purpose", "created_at"],
        schema="identity",
    )

    # Membership uniqueness + FKs (best-effort; orphan rows fail upgrade — Phase 1 DBs are empty/dev)
    op.create_foreign_key(
        "fk_org_memberships_user",
        "org_memberships",
        "users",
        ["user_id"],
        ["id"],
        source_schema="tenant",
        referent_schema="identity",
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_org_memberships_org_user",
        "org_memberships",
        ["organization_id", "user_id"],
        schema="tenant",
    )
    op.create_foreign_key(
        "fk_tenant_memberships_user",
        "tenant_memberships",
        "users",
        ["user_id"],
        ["id"],
        source_schema="tenant",
        referent_schema="identity",
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_tenant_memberships_tenant_user",
        "tenant_memberships",
        ["tenant_id", "user_id"],
        schema="tenant",
    )

    op.create_foreign_key(
        "fk_resources_created_by_principal",
        "resources",
        "principals",
        ["created_by_principal_id"],
        ["id"],
        source_schema="resource",
        referent_schema="identity",
        ondelete="SET NULL",
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION authz.prevent_principal_role_scope_mismatch()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          role_scope text;
          role_tenant uuid;
          role_operator uuid;
        BEGIN
          SELECT r.scope_type, r.tenant_id, r.operator_org_id
            INTO role_scope, role_tenant, role_operator
          FROM authz.roles r WHERE r.id = NEW.role_id;

          IF role_scope IS DISTINCT FROM NEW.scope_type THEN
            RAISE EXCEPTION 'principal_roles.scope_type must match roles.scope_type';
          END IF;
          IF NEW.scope_type = 'tenant' AND (NEW.tenant_id IS DISTINCT FROM role_tenant) THEN
            RAISE EXCEPTION 'principal_roles.tenant_id must match roles.tenant_id';
          END IF;
          IF NEW.scope_type = 'platform' AND (NEW.operator_org_id IS DISTINCT FROM role_operator) THEN
            RAISE EXCEPTION 'principal_roles.operator_org_id must match roles.operator_org_id';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_principal_roles_scope_guard ON authz.principal_roles")
    op.execute(
        """
        CREATE TRIGGER trg_principal_roles_scope_guard
        BEFORE INSERT OR UPDATE ON authz.principal_roles
        FOR EACH ROW
        EXECUTE PROCEDURE authz.prevent_principal_role_scope_mismatch()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_principal_roles_scope_guard ON authz.principal_roles")
    op.execute("DROP FUNCTION IF EXISTS authz.prevent_principal_role_scope_mismatch()")
    op.drop_constraint("fk_resources_created_by_principal", "resources", schema="resource", type_="foreignkey")
    op.drop_constraint("uq_tenant_memberships_tenant_user", "tenant_memberships", schema="tenant", type_="unique")
    op.drop_constraint("fk_tenant_memberships_user", "tenant_memberships", schema="tenant", type_="foreignkey")
    op.drop_constraint("uq_org_memberships_org_user", "org_memberships", schema="tenant", type_="unique")
    op.drop_constraint("fk_org_memberships_user", "org_memberships", schema="tenant", type_="foreignkey")
    op.drop_index("ix_delivery_secrets_purpose_created", table_name="delivery_secrets", schema="identity")
    op.drop_table("delivery_secrets", schema="identity")
