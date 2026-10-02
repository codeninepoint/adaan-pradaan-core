# Roles, authorization, and statuses

This is the single reference for who can do what, and which status values the running system uses. It follows the code in `src/`, not the longer design docs.

Those design docs still describe extra states and APIs that are not built yet. They are listed at the end so you can tell the two apart.

## How the pieces fit

Signup creates one organization. That organization is an **individual**. It is also a **consumer**. It is not a vendor until someone registers a vendor profile.

| Idea | Where it lives | What it means |
|------|----------------|---------------|
| Organization type | `tenant.organizations.org_type` | `individual` or `organization`. There is no third type called vendor. |
| Participation | `tenant.organizations.participation` | Whether the org only consumes the platform, or also sells on it. |
| Platform operator | `tenant.organizations.is_platform_operator` | Whether members of this org may review vendor applications. |
| Org membership role | `tenant.org_memberships.role` | Governance of the organization (`owner` or `member`). This is not an RBAC grant. |
| RBAC role | `authz.roles` + `authz.principal_roles` | The permission bundle checked on API calls. Roles are not stored in the JWT. |
| Tenant | `tenant.tenants` | Isolation boundary under the organization. Signup creates one default tenant. |
| Project | `tenant.projects` | A row under a tenant. Signup creates `default-project`. There is no project API yet. |
| Workspace | not an entity | Signup names the org “{display name} workspace”. A resource may use `resource_type = workspace`. That is a label, not a lifecycle. |

```text
User
  └── Organization          org_type, participation, is_platform_operator, status
        ├── Org membership  role: owner | member, status
        ├── Vendor profile  optional, one per org
        └── Tenant          status
              ├── Tenant membership   status
              ├── Project             status (default-project only)
              ├── RBAC roles          tenant-admin, resource-admin, viewer
              ├── Service account     machine principal + API key, same tenant roles
              └── Resource            name + resource_type (workspace is one possible type)
```

## Organization type, participation, and vendor

`org_type` and `participation` change independently.

| Path | `org_type` after | `participation` after | Vendor profile |
|------|------------------|------------------------|----------------|
| Signup | `individual` | `consumer` | none |
| Register as vendor (individual or organization) | unchanged | `consumer_and_vendor` | `pending_verification` |
| Upgrade individual to organization | `organization` | unchanged | kept if one already exists |
| Vendor application rejected | unchanged | rolled back to `consumer` | profile stays, status `rejected` |
| Already an organization, upgrade again | forbidden | — | — |
| Second vendor register on the same org | — | — | 409, one profile per org |

`keycloak_realm_ref` is empty for an individual. An organization upgrade sets it to the org slug and creates a dedicated Keycloak realm. The slug does not change after that.

`participation` values the code writes: `consumer`, `consumer_and_vendor`. The design docs also mention a bare `vendor` value. Signup and vendor registration do not write that value.

### Platform operator

An organization with `is_platform_operator = true` is the operator of this deployment. Customer orgs stay `false`.

The flag is set when a signed-in user calls `GET /auth/me` and their email is in `TENANT_PLATFORM_OPERATOR_EMAILS`, and they are an **owner** of that organization. `GET /auth/me` then returns `is_platform_operator: true`.

Vendor approve and reject do not check an RBAC permission code. They require an active membership in an organization that has this flag. Otherwise the call is 403.

## Statuses the code writes

### User and principal

| Record | Values the code sets | Meaning |
|--------|----------------------|---------|
| `identity.users.status` | `pending_verification` → `active`, or `locked` | Signup leaves the user at `pending_verification`. Email verify sets `active`. Login is refused until then. Lock sets `locked`. |
| `identity.principals.status` | `inactive` → `active`, or `locked` | `principal_type` is `user` or `service_account`. A user principal stays `inactive` until email verify. A service account principal starts `active`. |
| `identity.sessions.status` | `active`, `revoked` | Sign-out and admin revoke set `revoked`. |
| `identity.credentials.status` | `active` | Password credential created at signup. |

### Organization, tenant, project, membership

| Record | Values the code sets | Meaning |
|--------|----------------------|---------|
| `tenant.organizations.status` | `active` | Signup and org upgrade both leave the org `active`. Design docs also describe `provisioning`, `suspended`, and `closed`. Those transitions are not implemented. |
| `tenant.organizations.org_type` | `individual`, `organization` | See the table above. |
| `tenant.organizations.participation` | `consumer`, `consumer_and_vendor` | See the table above. |
| `tenant.org_memberships.role` | `owner`, `member` | Signup makes the registering user `owner`. An owner may invite another existing user as `member` or `owner`. |
| `tenant.org_memberships.status` | `active`, `invited`, `removed` | Invite creates `invited`. Accept sets `active`. Remove sets `removed`. |
| `tenant.tenants.status` | `active` | Default tenant on signup, and the `{slug}-default` tenant on org upgrade. |
| `tenant.tenant_memberships.status` | `active`, `removed` | Membership in a tenant. This table has no role column. Permissions come from RBAC bindings. |
| `tenant.projects.status` | `active` | Only `default-project` is created (signup and org upgrade). No archive or delete path, and no project HTTP API. |
| `tenant.organization_registration_requests.status` | `processing`, `completed`, `failed` | Org upgrade. Inline mode finishes as `completed` in the same request. Temporal mode returns `processing` until the worker finishes. |

### Vendor

| Record | Values the code sets | Meaning |
|--------|----------------------|---------|
| `vendor.profiles.status` | `pending_verification`, `verified`, `rejected` | Set to `pending_verification` on register. Approve sets `verified`. Reject sets `rejected`. |
| `vendor.verifications.status` | `queued`, then `approved` or `rejected` | Register inserts `queued`. The review queue also treats `pending` as still waiting. A decision on any other status is 409. |

The applicant page shows the profile status (`pending_verification`, `verified`, `rejected`) and the verification notes when a reject included them.

### Resource and “workspace”

| Record | Values the code sets | Meaning |
|--------|----------------------|---------|
| `resource.resources.status` | `active` | Create always stores `active`. |
| `resource.resources.resource_type` | any string, for example `workspace` | Not a status. `workspace` is one allowed label used by the UI and tests. It does not create a workspace entity. |

There is no project-scoped resource. A resource belongs to a tenant.

### Service account

A service account is a machine principal in one tenant. It is not a user: no email, no Keycloak login, no organization membership, and no tenant membership row. It is stored as `identity.service_accounts` plus `identity.principals` with `principal_type = service_account`. The principal starts `active`.

The account status the code writes is only `active`. List, role assign, key rotate, and key revoke all require that status. There is no disable or delete path.

The name is stored lowercase. It must match `^[a-z][a-z0-9-]{1,62}[a-z0-9]$` and be unique in the tenant. A duplicate name is 409. The tenant must be `active`.

| Record | Values the code sets | Meaning |
|--------|----------------------|---------|
| `identity.service_accounts.status` | `active` | Created active. Later calls treat any other status as not found. |
| `identity.principals` for the account | `active` | Starts active. A user principal stays inactive until email verify. |
| `identity.api_keys.status` | `active`, `revoked` | One active key at a time. Rotate and revoke set the old key to `revoked`. |

API key (`identity.api_keys`):

- Create issues one key and returns the raw value once. Only `key_hash` and a prefix (`ak_` plus 8 hex characters) are stored.
- Rotate sets the current active key to `revoked` and inserts a new `active` key. The new raw value is returned once.
- Revoke sets that key to `revoked`. A second revoke is 409.

Authorization:

- List, create, assign role, rotate, and revoke all require a signed-in user with `tenant.admin` in that tenant. The screen is `/app/service-accounts`.
- Optional `initial_role` on create binds one active tenant role to the service-account principal (`scope_type = tenant`). The UI sends `resource-admin`.
- A later assign uses a role id in the same tenant. A second active binding of the same role is 409.
- After that binding, the service account passes the same `authorize()` checks as a user who holds that role.
- The API key is not accepted as a Bearer token. Callers of the management APIs still use a user access token.

### RBAC records

| Record | Values the code sets |
|--------|----------------------|
| `authz.permissions.status`, `authz.roles.status` | `active` |
| `authz.principal_roles.status` | `active`, `revoked` |

## Authorization

The access token carries the user (`sub`, `uid`, `pid`) and expiry. It does not carry roles. Each protected call looks up `authz.principal_roles` for that principal in the tenant from `X-Tenant-Id`.

Tenant-scoped roles never receive `platform.*` permissions, and platform-scoped roles never receive tenant permissions.

### Roles seeded for each tenant

The registering user is bound to `tenant-admin` on the default tenant.

| Role | Permissions |
|------|-------------|
| `tenant-admin` | `resource.read`, `resource.create`, `resource.update`, `resource.delete`, `tenant.member.read`, `tenant.member.invite`, `tenant.member.revoke`, `tenant.settings.update`, `vendor.read`, `vendor.manage`, `billing.invoice.read`, plus compat codes `tenant.admin`, `resource.allocation.create`, `resource.allocation.approve`, `audit.read` |
| `resource-admin` | `resource.read`, `resource.create`, `resource.update`, `resource.delete`, `vendor.read`, `vendor.manage`, `resource.allocation.create`, `resource.allocation.approve` |
| `viewer` | `resource.read`, `tenant.member.read`, `vendor.read`, `billing.invoice.read` |

Platform-scoped templates exist in the catalog. They are not what the vendor review screen uses.

| Platform role | Permissions |
|---------------|-------------|
| `platform-admin` | `platform.tenant.read`, `platform.tenant.suspend` |
| `platform-support` | `platform.tenant.read` |

### What an API call actually checks

| Action | Check |
|--------|--------|
| List resources | `resource.read` in the tenant |
| Create a resource | `resource.create` in the tenant |
| Invite or remove a tenant member, grant or revoke a tenant role | `tenant.admin` in the tenant |
| List, create, assign a role, rotate, or revoke a service account key | `tenant.admin` in the tenant. See Service account above. |
| Invite, accept, or remove an organization member | caller’s org membership role is `owner` |
| Register a vendor | caller is an owner of that org, and the org does not already have a vendor profile |
| List the vendor review queue, approve, or reject | active membership in an org with `is_platform_operator = true` |

These catalog codes are seeded but no route calls `authorize()` with them yet: `resource.update`, `resource.delete`, `tenant.member.read`, `tenant.member.invite`, `tenant.member.revoke`, `tenant.settings.update`, `vendor.read`, `vendor.manage`, `billing.invoice.read`, `platform.tenant.read`, `platform.tenant.suspend`.

Grant and revoke of tenant roles are available on `/app/members`. Vendor review is available on `/app/vendor` for a platform operator.

## Where the longer design docs live

Use this file for the current behavior. The documents below describe the intended model and include states and APIs that are not implemented (project create, tenant suspend, workspace as its own aggregate, `platform.vendor.verify`, and so on).

| Topic | Document |
|-------|----------|
| Org type, participation, tenant and project lifecycle (design) | [docs/domains/tenant-domain.md](domains/tenant-domain.md) |
| RBAC catalog and evaluation (design, wider than the seeded catalog) | [docs/domains/authorization-domain.md](domains/authorization-domain.md) |
| Platform operator and management plane (design) | [docs/architecture/management-plane.md](architecture/management-plane.md) |
| Identity, sessions, realms | [docs/domains/identity-domain.md](domains/identity-domain.md) |
| Vendor and plugin marketplace (mostly not built) | [docs/domains/vendor-plugin-domain.md](domains/vendor-plugin-domain.md) |
| Journeys, including project create (J13, not built) | [docs/User_Journeys/02_Tenant_Vendor_Plugin_Journeys.md](User_Journeys/02_Tenant_Vendor_Plugin_Journeys.md) |
| Which HTTP routes exist today | [docs/API_UI_CORS_GUIDE.md](API_UI_CORS_GUIDE.md) |

The permission list in code is `src/authz/domain/catalog.py`. Status writes are in `src/identity/application/identity_service.py`, `src/identity/application/service_accounts.py`, `src/tenant/application/org_upgrade.py`, `src/tenant/application/members.py`, and `src/vendor/application/vendor_service.py`.
