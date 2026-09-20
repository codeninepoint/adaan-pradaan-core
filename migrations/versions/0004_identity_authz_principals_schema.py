"""0004 identity authz principals schema

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07

Evolves identity/authz toward principals-centric model with explicit
tenant_id/operator_org_id scope columns (no polymorphic scope_id).
Drops sessions.refresh_token_hash (Phase 1 J4 refresh breaks until Prompt 3).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- principals ---
    op.create_table(
        "principals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "principal_type IN ('user', 'service_account')",
            name="ck_principals_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'inactive', 'locked', 'revoked')",
            name="ck_principals_status",
        ),
        schema="identity",
    )
    op.create_index(
        "ix_principals_type_status",
        "principals",
        ["principal_type", "status"],
        schema="identity",
    )

    # Backfill principals from users (id reuse = principal_id for simplicity)
    op.execute(
        """
        INSERT INTO identity.principals (id, principal_type, status, created_at, updated_at)
        SELECT id, 'user',
               CASE
                 WHEN status = 'locked' THEN 'locked'
                 WHEN status IN ('active', 'pending_verification') THEN 'active'
                 ELSE 'inactive'
               END,
               created_at, updated_at
        FROM identity.users
        """
    )
    op.execute(
        """
        INSERT INTO identity.principals (id, principal_type, status, created_at, updated_at)
        SELECT id, 'service_account',
               CASE WHEN status = 'active' THEN 'active' ELSE 'revoked' END,
               created_at, created_at
        FROM identity.service_accounts
        ON CONFLICT (id) DO NOTHING
        """
    )

    # --- users: principal_id + normalized_email ---
    op.add_column(
        "users",
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="identity",
    )
    op.add_column(
        "users",
        sa.Column("normalized_email", sa.String(255), nullable=True),
        schema="identity",
    )
    op.execute("UPDATE identity.users SET principal_id = id, normalized_email = lower(email)")
    op.alter_column("users", "principal_id", nullable=False, schema="identity")
    op.alter_column("users", "normalized_email", nullable=False, schema="identity")
    op.create_foreign_key(
        "fk_users_principal",
        "users",
        "principals",
        ["principal_id"],
        ["id"],
        source_schema="identity",
        referent_schema="identity",
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_users_principal_id", "users", ["principal_id"], schema="identity")
    op.create_unique_constraint("uq_users_normalized_email", "users", ["normalized_email"], schema="identity")
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('pending_verification', 'active', 'locked', 'deactivated')",
        schema="identity",
    )

    # --- identity_realms: issuer + checks ---
    op.add_column(
        "identity_realms",
        sa.Column("issuer", sa.String(512), nullable=True),
        schema="identity",
    )
    op.add_column(
        "identity_realms",
        sa.Column("keycloak_realm_id", sa.String(255), nullable=True),
        schema="identity",
    )
    op.execute("UPDATE identity.identity_realms SET issuer = issuer_url")
    op.alter_column("identity_realms", "issuer", nullable=False, schema="identity")
    op.create_unique_constraint("uq_identity_realms_issuer", "identity_realms", ["issuer"], schema="identity")
    op.create_check_constraint(
        "ck_identity_realms_type",
        "identity_realms",
        "realm_type IN ('platform', 'organization', 'operator')",
        schema="identity",
    )
    op.execute(
        """
        UPDATE identity.identity_realms
        SET status = 'active'
        WHERE status NOT IN ('provisioning', 'active', 'suspended', 'deprovisioned')
        """
    )
    op.create_check_constraint(
        "ck_identity_realms_status",
        "identity_realms",
        "status IN ('provisioning', 'active', 'suspended', 'deprovisioned')",
        schema="identity",
    )
    op.create_check_constraint(
        "ck_identity_realms_org_binding",
        "identity_realms",
        """
        (realm_type = 'organization' AND organization_id IS NOT NULL)
        OR (realm_type IN ('platform', 'operator') AND organization_id IS NULL)
        """,
        schema="identity",
    )
    op.create_index(
        "ix_identity_realms_organization_id",
        "identity_realms",
        ["organization_id"],
        schema="identity",
    )
    op.create_foreign_key(
        "fk_identity_realms_organization",
        "identity_realms",
        "organizations",
        ["organization_id"],
        ["id"],
        source_schema="identity",
        referent_schema="tenant",
        ondelete="SET NULL",
    )

    # --- credentials: rebuild to principal_id + identity_realm_id ---
    op.rename_table("credentials", "credentials_legacy", schema="identity")
    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.principals.id"), nullable=False),
        sa.Column(
            "identity_realm_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity.identity_realms.id"),
            nullable=False,
        ),
        sa.Column("keycloak_subject", sa.String(255), nullable=False),
        sa.Column("credential_type", sa.String(32), nullable=False, server_default="password_delegated"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("identity_realm_id", "keycloak_subject", name="uq_credentials_realm_subject"),
        sa.CheckConstraint(
            "credential_type IN ('oidc', 'password_delegated', 'federated')",
            name="ck_credentials_type",
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_credentials_status"),
        schema="identity",
    )
    op.create_index(
        "ix_credentials_principal_status",
        "credentials",
        ["principal_id", "status"],
        schema="identity",
    )
    op.execute(
        """
        INSERT INTO identity.credentials (
            id, principal_id, identity_realm_id, keycloak_subject, credential_type, status, created_at, updated_at
        )
        SELECT c.id, c.user_id, r.id, c.keycloak_subject, 'password_delegated', 'active', c.created_at, c.created_at
        FROM identity.credentials_legacy c
        JOIN identity.identity_realms r ON r.realm_name = c.realm_ref
        """
    )
    op.drop_table("credentials_legacy", schema="identity")

    # --- service_accounts ---
    op.add_column(
        "service_accounts",
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="identity",
    )
    op.add_column(
        "service_accounts",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="identity",
    )
    op.add_column(
        "service_accounts",
        sa.Column("created_by_principal_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="identity",
    )
    op.execute("UPDATE identity.service_accounts SET principal_id = id")
    # Best-effort org from tenant
    op.execute(
        """
        UPDATE identity.service_accounts sa
        SET organization_id = t.organization_id
        FROM tenant.tenants t
        WHERE t.id = sa.tenant_id
        """
    )
    # If no tenant match, leave null then fail — set a placeholder only if rows exist without org
    op.execute(
        """
        UPDATE identity.service_accounts
        SET organization_id = '00000000-0000-4000-8000-000000000099'
        WHERE organization_id IS NULL
        """
    )
    # Ensure placeholder org exists only if needed
    op.execute(
        """
        INSERT INTO tenant.organizations (id, name, slug, org_type, participation, status)
        SELECT '00000000-0000-4000-8000-000000000099', 'sa-orphan-placeholder', 'sa-orphan-placeholder',
               'individual', 'consumer', 'active'
        WHERE EXISTS (
            SELECT 1 FROM identity.service_accounts
            WHERE organization_id = '00000000-0000-4000-8000-000000000099'
        )
        AND NOT EXISTS (
            SELECT 1 FROM tenant.organizations WHERE id = '00000000-0000-4000-8000-000000000099'
        )
        """
    )
    op.alter_column("service_accounts", "principal_id", nullable=False, schema="identity")
    op.alter_column("service_accounts", "organization_id", nullable=False, schema="identity")
    op.create_foreign_key(
        "fk_sa_principal",
        "service_accounts",
        "principals",
        ["principal_id"],
        ["id"],
        source_schema="identity",
        referent_schema="identity",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_sa_created_by",
        "service_accounts",
        "principals",
        ["created_by_principal_id"],
        ["id"],
        source_schema="identity",
        referent_schema="identity",
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sa_tenant",
        "service_accounts",
        "tenants",
        ["tenant_id"],
        ["id"],
        source_schema="identity",
        referent_schema="tenant",
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_sa_organization",
        "service_accounts",
        "organizations",
        ["organization_id"],
        ["id"],
        source_schema="identity",
        referent_schema="tenant",
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_sa_principal_id", "service_accounts", ["principal_id"], schema="identity")
    op.create_unique_constraint("uq_sa_tenant_name", "service_accounts", ["tenant_id", "name"], schema="identity")
    op.create_check_constraint(
        "ck_sa_status",
        "service_accounts",
        "status IN ('active', 'revoked')",
        schema="identity",
    )
    op.create_index(
        "ix_sa_tenant_status",
        "service_accounts",
        ["tenant_id", "status"],
        schema="identity",
    )

    # --- api_keys ---
    op.alter_column(
        "api_keys",
        "key_prefix",
        new_column_name="prefix",
        schema="identity",
    )
    op.create_check_constraint(
        "ck_api_keys_status",
        "api_keys",
        "status IN ('active', 'revoked')",
        schema="identity",
    )
    op.create_index(
        "ix_api_keys_sa_status",
        "api_keys",
        ["service_account_id", "status"],
        schema="identity",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_api_keys_active_prefix
        ON identity.api_keys (prefix)
        WHERE status = 'active'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_api_keys_one_active_per_sa
        ON identity.api_keys (service_account_id)
        WHERE status = 'active'
        """
    )

    # --- drop refresh_token_hash (J4 transitional break) ---
    op.drop_column("sessions", "refresh_token_hash", schema="identity")

    # --- permissions ---
    op.alter_column(
        "permissions",
        "scope",
        new_column_name="scope_type",
        schema="authz",
    )
    op.add_column(
        "permissions",
        sa.Column("description", sa.Text(), nullable=True),
        schema="authz",
    )
    op.add_column(
        "permissions",
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        schema="authz",
    )
    op.create_check_constraint(
        "ck_permissions_scope_type",
        "permissions",
        "scope_type IN ('tenant', 'platform')",
        schema="authz",
    )
    op.create_check_constraint(
        "ck_permissions_platform_prefix",
        "permissions",
        """
        (scope_type = 'platform' AND code LIKE 'platform.%')
        OR (scope_type = 'tenant' AND code NOT LIKE 'platform.%')
        """,
        schema="authz",
    )
    op.create_check_constraint(
        "ck_permissions_status",
        "permissions",
        "status IN ('active', 'deprecated')",
        schema="authz",
    )

    # --- roles: explicit tenant_id / operator_org_id ---
    op.add_column(
        "roles",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="authz",
    )
    op.add_column(
        "roles",
        sa.Column("operator_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="authz",
    )
    op.add_column(
        "roles",
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        schema="authz",
    )
    op.alter_column(
        "roles",
        "is_system",
        new_column_name="is_system_role",
        schema="authz",
    )
    op.execute(
        """
        UPDATE authz.roles
        SET tenant_id = scope_id
        WHERE scope_type = 'tenant'
        """
    )
    op.execute(
        """
        UPDATE authz.roles
        SET operator_org_id = scope_id
        WHERE scope_type = 'platform'
        """
    )
    op.drop_constraint("uq_role_scope_name", "roles", schema="authz", type_="unique")
    op.drop_column("roles", "scope_id", schema="authz")
    op.create_check_constraint(
        "ck_roles_scope_type",
        "roles",
        "scope_type IN ('tenant', 'platform')",
        schema="authz",
    )
    op.create_check_constraint(
        "ck_roles_scope_xor",
        "roles",
        """
        (scope_type = 'tenant' AND tenant_id IS NOT NULL AND operator_org_id IS NULL)
        OR (scope_type = 'platform' AND tenant_id IS NULL AND operator_org_id IS NOT NULL)
        """,
        schema="authz",
    )
    op.create_check_constraint(
        "ck_roles_status",
        "roles",
        "status IN ('active', 'deprecated')",
        schema="authz",
    )
    op.create_foreign_key(
        "fk_roles_tenant",
        "roles",
        "tenants",
        ["tenant_id"],
        ["id"],
        source_schema="authz",
        referent_schema="tenant",
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_roles_operator_org",
        "roles",
        "organizations",
        ["operator_org_id"],
        ["id"],
        source_schema="authz",
        referent_schema="tenant",
        ondelete="CASCADE",
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_roles_tenant_name
        ON authz.roles (scope_type, tenant_id, name)
        WHERE scope_type = 'tenant'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_roles_platform_name
        ON authz.roles (scope_type, operator_org_id, name)
        WHERE scope_type = 'platform'
        """
    )

    # --- role_permissions: prefer RESTRICT (already FK); ensure unique ---
    # already has uq_role_permission

    # --- principal_roles (replace user_roles) ---
    op.create_table(
        "principal_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.principals.id"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authz.roles.id"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.tenants.id"), nullable=True),
        sa.Column(
            "operator_org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant.organizations.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.principals.id"), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("scope_type IN ('tenant', 'platform')", name="ck_principal_roles_scope_type"),
        sa.CheckConstraint(
            """
            (scope_type = 'tenant' AND tenant_id IS NOT NULL AND operator_org_id IS NULL)
            OR (scope_type = 'platform' AND tenant_id IS NULL AND operator_org_id IS NOT NULL)
            """,
            name="ck_principal_roles_scope_xor",
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_principal_roles_status"),
        schema="authz",
    )
    op.execute(
        """
        INSERT INTO authz.principal_roles (
            id, principal_id, role_id, scope_type, tenant_id, operator_org_id,
            status, assigned_by, valid_from, valid_until, revoked_at, justification, created_at
        )
        SELECT
            ur.id,
            ur.user_id,
            ur.role_id,
            ur.scope_type,
            CASE WHEN ur.scope_type = 'tenant' THEN ur.scope_id ELSE NULL END,
            CASE WHEN ur.scope_type = 'platform' THEN ur.scope_id ELSE NULL END,
            ur.status,
            ur.granted_by,
            ur.granted_at,
            ur.expires_at,
            ur.revoked_at,
            ur.justification,
            ur.granted_at
        FROM authz.user_roles ur
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_principal_roles_active_tenant
        ON authz.principal_roles (principal_id, role_id, tenant_id)
        WHERE status = 'active' AND tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_principal_roles_active_platform
        ON authz.principal_roles (principal_id, role_id, operator_org_id)
        WHERE status = 'active' AND operator_org_id IS NOT NULL
        """
    )
    op.drop_table("user_roles", schema="authz")

    # --- authorization_audit_log ---
    op.create_table(
        "authorization_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.principals.id"), nullable=True),
        sa.Column("permission_code", sa.String(128), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("operator_org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("scope_type IN ('tenant', 'platform')", name="ck_aal_scope_type"),
        sa.CheckConstraint("decision IN ('allow', 'deny')", name="ck_aal_decision"),
        sa.CheckConstraint(
            """
            (scope_type = 'tenant' AND tenant_id IS NOT NULL AND operator_org_id IS NULL)
            OR (scope_type = 'platform' AND tenant_id IS NULL AND operator_org_id IS NOT NULL)
            OR (tenant_id IS NULL AND operator_org_id IS NULL)
            """,
            name="ck_aal_scope_xor",
        ),
        schema="authz",
    )
    op.create_index(
        "ix_aal_principal_created",
        "authorization_audit_log",
        ["principal_id", "created_at"],
        schema="authz",
    )
    op.create_index(
        "ix_aal_permission_created",
        "authorization_audit_log",
        ["permission_code", "created_at"],
        schema="authz",
    )


def downgrade() -> None:
    op.drop_table("authorization_audit_log", schema="authz")

    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_type", sa.String(32), nullable=False, server_default="user"),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("authz.roles.id"), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("justification", sa.Text(), nullable=True),
        schema="authz",
    )
    op.execute(
        """
        INSERT INTO authz.user_roles (
            id, user_id, principal_type, role_id, scope_type, scope_id, status,
            granted_by, granted_at, revoked_at, expires_at, justification
        )
        SELECT
            id, principal_id, 'user', role_id, scope_type,
            COALESCE(tenant_id, operator_org_id),
            status, assigned_by, valid_from, revoked_at, valid_until, justification
        FROM authz.principal_roles
        """
    )
    op.drop_table("principal_roles", schema="authz")

    op.execute("DROP INDEX IF EXISTS authz.uq_roles_tenant_name")
    op.execute("DROP INDEX IF EXISTS authz.uq_roles_platform_name")
    op.drop_constraint("fk_roles_operator_org", "roles", schema="authz", type_="foreignkey")
    op.drop_constraint("fk_roles_tenant", "roles", schema="authz", type_="foreignkey")
    op.drop_constraint("ck_roles_status", "roles", schema="authz", type_="check")
    op.drop_constraint("ck_roles_scope_xor", "roles", schema="authz", type_="check")
    op.drop_constraint("ck_roles_scope_type", "roles", schema="authz", type_="check")
    op.add_column(
        "roles",
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="authz",
    )
    op.execute(
        """
        UPDATE authz.roles
        SET scope_id = COALESCE(tenant_id, operator_org_id)
        """
    )
    op.alter_column("roles", "scope_id", nullable=False, schema="authz")
    op.alter_column("roles", "is_system_role", new_column_name="is_system", schema="authz")
    op.drop_column("roles", "status", schema="authz")
    op.drop_column("roles", "operator_org_id", schema="authz")
    op.drop_column("roles", "tenant_id", schema="authz")
    op.create_unique_constraint(
        "uq_role_scope_name",
        "roles",
        ["scope_type", "scope_id", "name"],
        schema="authz",
    )

    op.drop_constraint("ck_permissions_status", "permissions", schema="authz", type_="check")
    op.drop_constraint("ck_permissions_platform_prefix", "permissions", schema="authz", type_="check")
    op.drop_constraint("ck_permissions_scope_type", "permissions", schema="authz", type_="check")
    op.drop_column("permissions", "status", schema="authz")
    op.drop_column("permissions", "description", schema="authz")
    op.alter_column("permissions", "scope_type", new_column_name="scope", schema="authz")

    op.add_column(
        "sessions",
        sa.Column("refresh_token_hash", sa.String(255), nullable=True),
        schema="identity",
    )

    op.execute("DROP INDEX IF EXISTS identity.uq_api_keys_one_active_per_sa")
    op.execute("DROP INDEX IF EXISTS identity.uq_api_keys_active_prefix")
    op.drop_index("ix_api_keys_sa_status", table_name="api_keys", schema="identity")
    op.drop_constraint("ck_api_keys_status", "api_keys", schema="identity", type_="check")
    op.alter_column(
        "api_keys",
        "prefix",
        new_column_name="key_prefix",
        schema="identity",
    )

    op.drop_index("ix_sa_tenant_status", table_name="service_accounts", schema="identity")
    op.drop_constraint("ck_sa_status", "service_accounts", schema="identity", type_="check")
    op.drop_constraint("uq_sa_tenant_name", "service_accounts", schema="identity", type_="unique")
    op.drop_constraint("uq_sa_principal_id", "service_accounts", schema="identity", type_="unique")
    op.drop_constraint("fk_sa_organization", "service_accounts", schema="identity", type_="foreignkey")
    op.drop_constraint("fk_sa_tenant", "service_accounts", schema="identity", type_="foreignkey")
    op.drop_constraint("fk_sa_created_by", "service_accounts", schema="identity", type_="foreignkey")
    op.drop_constraint("fk_sa_principal", "service_accounts", schema="identity", type_="foreignkey")
    op.drop_column("service_accounts", "created_by_principal_id", schema="identity")
    op.drop_column("service_accounts", "organization_id", schema="identity")
    op.drop_column("service_accounts", "principal_id", schema="identity")

    op.rename_table("credentials", "credentials_new", schema="identity")
    op.create_table(
        "credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("identity.users.id"), nullable=False),
        sa.Column("keycloak_subject", sa.String(255), nullable=False),
        sa.Column("realm_ref", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="identity",
    )
    op.execute(
        """
        INSERT INTO identity.credentials (id, user_id, keycloak_subject, realm_ref, created_at)
        SELECT c.id, c.principal_id, c.keycloak_subject, r.realm_name, c.created_at
        FROM identity.credentials_new c
        JOIN identity.identity_realms r ON r.id = c.identity_realm_id
        """
    )
    op.drop_table("credentials_new", schema="identity")

    op.drop_constraint("fk_identity_realms_organization", "identity_realms", schema="identity", type_="foreignkey")
    op.drop_index("ix_identity_realms_organization_id", table_name="identity_realms", schema="identity")
    op.drop_constraint("ck_identity_realms_org_binding", "identity_realms", schema="identity", type_="check")
    op.drop_constraint("ck_identity_realms_status", "identity_realms", schema="identity", type_="check")
    op.drop_constraint("ck_identity_realms_type", "identity_realms", schema="identity", type_="check")
    op.drop_constraint("uq_identity_realms_issuer", "identity_realms", schema="identity", type_="unique")
    op.drop_column("identity_realms", "keycloak_realm_id", schema="identity")
    op.drop_column("identity_realms", "issuer", schema="identity")

    op.drop_constraint("ck_users_status", "users", schema="identity", type_="check")
    op.drop_constraint("uq_users_normalized_email", "users", schema="identity", type_="unique")
    op.drop_constraint("uq_users_principal_id", "users", schema="identity", type_="unique")
    op.drop_constraint("fk_users_principal", "users", schema="identity", type_="foreignkey")
    op.drop_column("users", "normalized_email", schema="identity")
    op.drop_column("users", "principal_id", schema="identity")

    op.drop_index("ix_principals_type_status", table_name="principals", schema="identity")
    op.drop_table("principals", schema="identity")
