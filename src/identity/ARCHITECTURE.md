# Identity bounded context — Phase 1 (J1–J6)

## Implemented journeys

| Journey | Endpoint(s) | Status |
|---------|-------------|--------|
| J1 | `POST /auth/register` | Done |
| J2 | `POST /auth/verify-email` | Done |
| J3 | `POST /auth/token` | Done — lean JWT + opaque refresh |
| J4 | `POST /auth/token/refresh` | Done — rotate + reuse detection |
| J5 | `DELETE /auth/session`, `/auth/sessions`, `/auth/sessions/{id}` | Done |
| J5b | `POST /auth/users/{id}/revoke-access` | Done — lock principal + kill sessions |
| J6 | `POST /auth/password/reset-request`, `/auth/password/reset` | Done |

Source of truth: [`docs/User_Journeys/Adanpradan_identity_auth_journeys.md`](../../docs/User_Journeys/Adanpradan_identity_auth_journeys.md)

Schema decision: [`docs/decisions/idr-002-identity-authz-schema.md`](../../docs/decisions/idr-002-identity-authz-schema.md)

## Architecture

```
identity/
  domain/           validators, exception re-exports
  application/      IdentityApplicationService (command handlers J1–J6)
  application/ports keycloak, tenant bootstrap contracts
  infrastructure/   ORM models, FakeKeycloakClient, bootstrap adapters
  interface/api/    FastAPI routes, Pydantic schemas, dependencies
```

Cross-context bootstrap for J1 (minimal, not full tenant/authz APIs):

- `TenantBootstrapAdapter` — creates individual org, tenant, project; seeds system roles + `principal_roles` binding
- `AuthzReader` — tenant permission checks via `principal_id` + explicit `tenant_id`

## JWT contract (J3)

Claims: `sub` (Keycloak subject), `iss`, `exp` (900s), `sid`, `typ`, `uid`, `pid`.  
**No** `roles` or `permissions` in token — AuthZ is live DB lookup every request.

Refresh: opaque `refresh_token` returned at login; only `bcrypt` hash stored on `identity.sessions`.  
On refresh: rotate hash; reuse of an old refresh revokes the session (theft signal).

## Database schemas

| Schema | Tables |
|--------|--------|
| `identity` | principals, users, credentials, identity_realms, sessions, audit_log, verification_tokens, password_reset_tokens, service_accounts, api_keys |
| `tenant` | organizations, org_memberships, tenants, projects (bootstrap only) |
| `authz` | permissions, roles, role_permissions, principal_roles, authorization_audit_log |
| `platform` | outbox_events |

## Assumptions flagged for review

1. **`identity.verification_tokens`** — journey references OTP hash at registration; table name not explicit in journey doc.
2. **Python package `shared/`** — renamed from `platform/` to avoid stdlib `platform` import conflict; PostgreSQL schema remains `platform`.
3. **J3 `404 email not found`** — implemented as documented (unlike J6 enumeration-safe pattern).
4. **Keycloak** — `FakeKeycloakClient` in tests/dev; `RealKeycloakClient` stub deferred.
5. **J4** — refresh hash restored in migration `0009`; login issues access + refresh; rotation + reuse revoke.
6. **Security hardening (review remediations)** — delivery_secrets for OTP/reset; resolve gates; deny audit autonomous commit; public forbid details; membership FKs.

## Constraint appendix (Prompt 2)

### Global

| Rule | Why |
|------|-----|
| UUID PKs | Opaque IDs; no sequential enumeration |
| `timestamptz` | Avoid naive UTC bugs across regions |
| Soft status as `varchar` + CHECK | Queryable; DB enforces allowed values |
| Soft-delete via `status` / `revoked_at` | Never hard-delete role bindings for audit |

### identity.principals

| Constraint | Explanation |
|------------|-------------|
| CHECK `principal_type IN ('user','service_account')` | Only two principal kinds |
| CHECK `status IN ('active','inactive','locked','revoked')` | Auth status gate |
| Index `(principal_type, status)` | Active principal filters |

### identity.users

| Constraint | Explanation |
|------------|-------------|
| UNIQUE `principal_id` | One User per human principal |
| UNIQUE `normalized_email` | Case-insensitive uniqueness |
| CHECK status lifecycle | `pending_verification` / `active` / `locked` / `deactivated` |
| No `password_hash` | Keycloak is credential SoT |

### identity.credentials

| Constraint | Explanation |
|------------|-------------|
| UNIQUE `(identity_realm_id, keycloak_subject)` | Resolve `(iss,sub)` per realm |
| FK `principal_id`, `identity_realm_id` | AuthZ-facing identity + realm binding |
| No password / refresh columns | |

### identity.api_keys

| Constraint | Explanation |
|------------|-------------|
| `key_hash` NOT NULL; no raw key | Show-once at creation |
| Partial unique active `prefix` | Lookup without revealing hash |
| At most one active key per SA | J09 invariant |

### authz.roles / principal_roles

| Constraint | Explanation |
|------------|-------------|
| XOR `tenant_id` / `operator_org_id` | **No polymorphic `scope_id`** |
| Soft revoke on bindings | Domain J11 — no hard DELETE |

### authz.authorization_audit_log

| Constraint | Explanation |
|------------|-------------|
| Append-only | Decision forensics |
| Explicit nullable scope columns | Prefer over polymorphic audit payload alone |

### identity.sessions

| Column | Notes |
|--------|-------|
| id | JWT `sid` |
| user_id | FK |
| status | active/revoked |
| refresh_token_hash | bcrypt of opaque refresh (nullable after revoke) |
| expires_at | Session / refresh window |

## Run

```bash
docker compose up -d postgres
pip install -e ".[dev]"
alembic upgrade head
uvicorn api.main:app --reload --app-dir src
pytest tests/integration/identity/ -v
python scripts/export_openapi.py
```

## Next phase

- **Prompt 3 (remaining):** Real Keycloak JWT adapter (issuer JWKS) when `TENANT_KEYCLOAK_MODE=real`
- **Prompt 4:** `AuthorizationService.authorize` — done (`authz.application.AuthorizationService`)
- **Prompt 5:** permission seed catalog — done (`authz.domain.catalog` + migration `0006` + `scripts/seed_authz_catalog.py`)
- **Prompt 6:** resource vertical slice — done (`POST /api/v1/tenants/{tenant_id}/resources`)
