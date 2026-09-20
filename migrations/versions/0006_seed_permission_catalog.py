"""0006 seed permission catalog

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-07

Idempotent upsert of the AuthZ permission catalog and a DB guard that
prevents tenant-scoped roles from receiving platform permissions.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSIONS = (
    ("resource.read", "tenant", "List/read resources"),
    ("resource.create", "tenant", "Create resource records"),
    ("resource.update", "tenant", "Update resource records"),
    ("resource.delete", "tenant", "Delete resources"),
    ("tenant.member.read", "tenant", "List tenant members"),
    ("tenant.member.invite", "tenant", "Invite tenant members"),
    ("tenant.member.revoke", "tenant", "Revoke tenant membership"),
    ("tenant.settings.update", "tenant", "Update tenant settings"),
    ("vendor.read", "tenant", "Read vendor profile for tenant"),
    ("vendor.manage", "tenant", "Manage vendor settings for tenant"),
    ("billing.invoice.read", "tenant", "Read tenant invoices"),
    ("platform.tenant.read", "platform", "Read any tenant (management plane)"),
    ("platform.tenant.suspend", "platform", "Suspend a customer tenant"),
    # Phase 1 compat codes
    ("tenant.admin", "tenant", "Legacy tenant admin (compat)"),
    ("resource.allocation.create", "tenant", "Legacy allocation create (compat)"),
    ("resource.allocation.approve", "tenant", "Legacy allocation approve (compat)"),
    ("audit.read", "tenant", "Legacy tenant audit read (compat)"),
)


def upgrade() -> None:
    for code, scope_type, description in PERMISSIONS:
        op.execute(
            f"""
            INSERT INTO authz.permissions (id, code, scope_type, description, status)
            VALUES (
              gen_random_uuid(),
              '{code}',
              '{scope_type}',
              '{description.replace("'", "''")}',
              'active'
            )
            ON CONFLICT (code) DO UPDATE SET
              scope_type = EXCLUDED.scope_type,
              description = EXCLUDED.description,
              status = 'active'
            """
        )

    # Defense in depth: refuse role_permissions that would grant platform.* to a tenant role.
    # Use sa.text so PL/pgSQL RAISE placeholders stay as single '%' (not '%%').
    op.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION authz.prevent_tenant_role_platform_permission()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            DECLARE
              role_scope text;
              perm_scope text;
              perm_code text;
            BEGIN
              SELECT r.scope_type INTO role_scope FROM authz.roles r WHERE r.id = NEW.role_id;
              SELECT p.scope_type, p.code INTO perm_scope, perm_code
              FROM authz.permissions p WHERE p.id = NEW.permission_id;

              IF role_scope = 'tenant' AND (perm_scope = 'platform' OR perm_code LIKE 'platform.%') THEN
                RAISE EXCEPTION
                  'tenant-scoped role % cannot receive platform permission %',
                  NEW.role_id, perm_code;
              END IF;

              IF role_scope = 'platform' AND (perm_scope <> 'platform' OR perm_code NOT LIKE 'platform.%') THEN
                RAISE EXCEPTION
                  'platform-scoped role % cannot receive tenant permission %',
                  NEW.role_id, perm_code;
              END IF;

              RETURN NEW;
            END;
            $$;
            """
        )
    )
    op.execute("DROP TRIGGER IF EXISTS trg_role_permissions_scope_guard ON authz.role_permissions")
    op.execute(
        """
        CREATE TRIGGER trg_role_permissions_scope_guard
        BEFORE INSERT OR UPDATE ON authz.role_permissions
        FOR EACH ROW
        EXECUTE PROCEDURE authz.prevent_tenant_role_platform_permission()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_role_permissions_scope_guard ON authz.role_permissions")
    op.execute("DROP FUNCTION IF EXISTS authz.prevent_tenant_role_platform_permission()")
    # Leave permission rows in place — removing them would break existing role_permissions.
