# Identity & Authorization — Complete User Journey Reference

> **11 Journeys · Every API · Every Table · Every State Change**
> Multi-Tenant Cloud Platform — Phase 1

---

## Journey Index

| # | Journey | Actor | Key Tables |
|---|---------|-------|------------|
| J01 | User Registration | Anonymous user | users, credentials, sessions, identity_realms |
| J02 | Email Verification | Registered user (unverified) | users, audit_log |
| J03 | User Login | Verified user | credentials, sessions, users |
| J04 | Token Refresh | Logged-in user | sessions |
| J05 | Session Revocation / Logout | Logged-in user or admin | sessions, audit_log |
| J06 | Password Reset | Verified user (forgot password) | users, audit_log |
| J07 | Organization Upgrade (Indiv → Org) | Individual org owner | identity_realms, users, tenant.organizations, authz.roles, authz.user_roles |
| J08 | Service Account Creation | Tenant admin | service_accounts, api_keys, authz.user_roles, audit_log |
| J09 | API Key Rotation / Revocation | Tenant admin or SA owner | api_keys, audit_log |
| J10 | Role Assignment (Grant) | Tenant admin | authz.roles, authz.user_roles, authz.permissions, audit_log |
| J11 | Role Revocation | Tenant admin | authz.user_roles, audit_log |

> **How to read each journey:** Every journey shows the exact API calls (method + path + request body + response body), which database tables are read or written, and what state changes occur in each table. State changes shown as: `BEFORE → AFTER`.

---

## J01 — User Registration

| Field | Value |
|-------|-------|
| **Actor** | Anonymous visitor |
| **Trigger** | User submits email + password via sign-up form |
| **Outcome** | User row created (`pending_verification`) · Default org + tenant seeded · Verification email sent |

### Overview

Registration is a multi-domain orchestration. Identity creates the user in Keycloak and in its own tables, then emits a domain event. Tenant domain reacts by seeding the individual organization, default tenant, and default project. Authorization domain seeds the initial roles. This all happens synchronously within one request transaction.

### Tables Affected

`identity.users` · `identity.credentials` · `identity.identity_realms` · `tenant.organizations` · `tenant.org_memberships` · `tenant.tenants` · `authz.roles` · `authz.user_roles` · `identity.audit_log`

### API Call

**`POST /auth/register`** — Submit email + password. No authentication required.

**Request:**
```json
{
  "email": "alice@example.com",
  "password": "SecurePass123!",
  "display_name": "Alice Smith",
  "agreed_to_terms": true
}
```

**Response:**
```json
{
  "user_id": "user-uuid-alice-001",
  "org_id": "org-uuid-alice-001",
  "tenant_id": "ten-uuid-alice-001",
  "status": "pending_verification",
  "verification_email_sent": true
}
```

**HTTP Codes:** `201 Created` · `409 email already registered` · `422 password too weak / terms not accepted`

### Internal Pipeline (Single DB Transaction)

| Step | Domain | Action | DB Write |
|------|--------|--------|----------|
| 1 | Identity | Validate email uniqueness | `SELECT users WHERE email=? → 0 rows required` |
| 2 | Identity | Create user in Keycloak platform realm | Keycloak API call → returns `kc_subject` string |
| 3 | Identity | `INSERT identity.users` | `status='pending_verification'` |
| 4 | Identity | `INSERT identity.credentials` | `keycloak_subject + realm_ref='platform'` |
| 5 | Tenant | `INSERT tenant.organizations` | `org_type='individual', participation='consumer'` |
| 6 | Tenant | `INSERT tenant.org_memberships` | `user_id=alice, role='owner'` |
| 7 | Tenant | `INSERT tenant.tenants` | `slug='alice-default', status='pending'→'active'` |
| 8 | Tenant | `INSERT tenant.projects` | `name='default-project'` |
| 9 | AuthZ | `INSERT authz.roles` (tenant-admin, resource-admin, viewer) | `is_system=true, scope_id=alice-tenant-id` |
| 10 | AuthZ | `INSERT authz.user_roles` | alice → tenant-admin in alice-default tenant |
| 11 | Identity | Send verification email via outbox | `INSERT outbox_events (type='send_verification_email')` |
| 12 | Audit | `INSERT identity.audit_log` | `event_action='user.registered'` |

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.users.status` | — (row didn't exist) | `'pending_verification'` | `user.registered` |
| `identity.credentials` | — (row didn't exist) | `kc_subject + realm_ref` | `credential.created` |
| `tenant.organizations` | — (row didn't exist) | `org_type='individual'` | `org.created` |
| `tenant.tenants.status` | — (row didn't exist) | `'active'` | `tenant.created` |
| `authz.roles` | — (rows didn't exist) | 3 rows, `is_system=true` | `roles.seeded` |
| `authz.user_roles.status` | — (row didn't exist) | `'active'` (tenant-admin) | `role_binding.created` |

### Validation Rules

| Rule | Condition | Error if Fails |
|------|-----------|----------------|
| Email uniqueness | `SELECT COUNT(*) FROM identity.users WHERE email=?` must = 0 | `409` — `email already registered` |
| Password strength | Min 10 chars, 1 upper, 1 digit, 1 special | `422` — `password does not meet requirements` |
| Terms acceptance | `agreed_to_terms` must be `true` | `422` — `terms of service must be accepted` |
| Email format | RFC 5322 regex | `422` — `invalid email format` |
| Display name | 1–255 chars, not blank | `422` — `display_name is required` |

> ⚠️ The Keycloak user creation (step 2) is wrapped with a **compensating transaction**: if any DB write after step 2 fails, the Keycloak user is deleted in the rollback handler. This prevents orphaned Keycloak users with no matching platform user row.

---

## J02 — Email Verification

| Field | Value |
|-------|-------|
| **Actor** | Registered user (`status: pending_verification`) |
| **Trigger** | User clicks link in email or submits 6-digit OTP code |
| **Outcome** | `users.status → active` · User can now log in |

### Overview

The verification token / OTP is a short-lived signed token generated at registration time and stored as a hash. When the user submits it, the hash is compared. On match, the user's status moves from `pending_verification` to `active`. This is the **only way** to reach the `active` state.

### Tables Affected

`identity.users` · `identity.audit_log`

### API Call

**`POST /auth/verify-email`** — Submit the 6-digit OTP from the verification email. No auth required.

**Request:**
```json
{
  "email": "alice@example.com",
  "otp_code": "472891"
}
```

**Response:**
```json
{
  "user_id": "user-uuid-alice-001",
  "status": "active",
  "message": "Email verified. You can now log in."
}
```

**HTTP Codes:** `200 OK` · `400 invalid or expired OTP` · `409 user already verified` · `404 email not found`

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.users.status` | `'pending_verification'` | `'active'` | `user.email_verified` |
| `identity.users.updated_at` | (previous timestamp) | `now()` | — |
| `identity.audit_log` | — | new row inserted | `user.email_verified` |

### `users.status` State Machine

| State | Meaning | Can Log In? | Next States Allowed |
|-------|---------|-------------|---------------------|
| `pending_verification` | Registered but email not confirmed | No | → `active` (via OTP) |
| `active` | Normal operating state | Yes | → `locked` (failed logins / admin) · → `deactivated` (admin) |
| `locked` | Too many failed logins or admin block | No | → `active` (admin unlock) |
| `deactivated` | Permanently disabled — **TERMINAL** | No | None — no reactivation |

> ✅ After verification the user can proceed to J03 (Login). A second call to `/auth/verify-email` returns `409` with `'user already verified'`.

---

## J03 — User Login

| Field | Value |
|-------|-------|
| **Actor** | Verified user (`status: active`) |
| **Trigger** | User submits email + password (or SSO redirect) |
| **Outcome** | JWT issued (15 min) · Refresh token issued · Session row created |

### Overview

Login has two sub-flows depending on realm type. Individual users and solo vendors authenticate against the **shared platform realm**. Organisation members authenticate against their company's **dedicated Keycloak realm**. The JWT contains **NO roles** — only `sub`, `iss`, `exp`, `sid`, `typ`.

### Tables Affected

`identity.users` · `identity.credentials` · `identity.sessions` · `identity.identity_realms` · `identity.audit_log`

### API Call

**`POST /auth/token`** — Exchange email + password for JWT. Realm auto-detected from email domain or explicit `realm_hint` param.

**Request:**
```json
{
  "email": "alice@example.com",
  "password": "••••••••",
  "realm_hint": "platform"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "ey...",
  "token_type": "Bearer",
  "expires_in": 900,
  "session_id": "session-uuid-001",
  "user_id": "user-uuid-alice-001"
}
```

**HTTP Codes:** `200 OK` · `401 invalid credentials` · `403 account locked or deactivated` · `404 email not found`

### Internal Flow

| Step | Action | Table Read / Written |
|------|--------|----------------------|
| 1 | Look up realm from email (or `realm_hint`) | `READ identity.identity_realms WHERE realm_name=?` |
| 2 | Validate credentials against Keycloak | Keycloak `/token` endpoint → returns `kc_subject` on success |
| 3 | Map `kc_subject` → `user_id` | `READ identity.credentials WHERE keycloak_subject=? AND realm_ref=?` |
| 4 | Check `users.status = 'active'` | `READ identity.users WHERE id=? → status must = 'active'` |
| 5 | Create session record | `INSERT identity.sessions (status='active', expires_at=now+7d)` |
| 6 | Store refresh token hash | `UPDATE identity.sessions SET refresh_token_hash=bcrypt(refresh_token)` |
| 7 | Build and sign JWT | JWT payload: `{sub, iss, exp, sid, typ}` — **NO roles** |
| 8 | Write audit log | `INSERT identity.audit_log (event_action='user.login')` |

### JWT Payload — What It Contains and What It Does NOT Contain

| Claim | Value | Purpose |
|-------|-------|---------|
| `sub` | `kc_subject` (Keycloak ID) | Looked up in `identity.credentials` to get `user_id` on every request |
| `iss` | Realm URL e.g. `acme.auth.platform.io` | Validated against `identity_realms`. Admin routes reject non-operator `iss`. |
| `exp` | Unix timestamp (`now + 900 sec`) | Token invalid after this. 15 min TTL. |
| `sid` | session UUID | Linked to `identity.sessions`. Used to check revocation. |
| `typ` | `'user'` or `'sa'` | Principal type. `'sa'` = service account API key auth. |
| `roles` | **NOT PRESENT** | Roles are **never** in JWT. Resolved from `authz.user_roles` DB on every request. |
| `permissions` | **NOT PRESENT** | Same reason. Instant revocation impossible if permissions are cached in token. |

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.sessions` | — (row didn't exist) | `status='active'` | `user.login` |
| `identity.sessions.refresh_token_hash` | — | `bcrypt(refresh_token)` | — |
| `identity.users.last_login_at` | (previous or NULL) | `now()` | — |
| `identity.audit_log` | — | new row inserted | `user.login` |

> ⚠️ Locked or deactivated users are rejected at step 4 with HTTP `403`. The error body does **not** distinguish between locked and deactivated — both return `'account is not accessible'` to prevent user enumeration.

---

## J04 — Token Refresh

| Field | Value |
|-------|-------|
| **Actor** | Logged-in user with valid refresh token |
| **Trigger** | Access token is expired (15 min) — client requests new one |
| **Outcome** | New access JWT issued (15 min) · Session `last_active_at` updated |

### Overview

Refresh tokens have a 7-day TTL and are **rotated on each use** — the old hash is overwritten with a new one. This means a stolen refresh token can only be used once before it is invalidated. If a session is revoked, the refresh fails immediately.

### Tables Affected

`identity.sessions` · `identity.audit_log`

### API Call

**`POST /auth/token/refresh`** — Exchange refresh token for new access token. No Bearer auth required.

**Request:**
```json
{
  "refresh_token": "ey...",
  "session_id": "session-uuid-001"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "ey...",
  "expires_in": 900
}
```

**HTTP Codes:** `200 OK` · `401 refresh token invalid / expired` · `403 session revoked` · `404 session not found`

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.sessions.status` | `'active'` | `'active'` (no change — checked only) | — |
| `identity.sessions.refresh_token_hash` | `bcrypt(old_tok)` | `bcrypt(new_tok)` — rotated | — |
| `identity.sessions.last_active_at` | (previous) | `now()` | — |

> ✅ Token rotation means: if an attacker steals the refresh token and uses it, the legitimate user's next refresh will fail (token hash mismatch). The session shows two simultaneous refresh attempts and should be auto-revoked.

---

## J05 — Session Revocation / Logout

| Field | Value |
|-------|-------|
| **Actor** | Logged-in user (self-logout) or Tenant/Platform admin (forced logout) |
| **Trigger** | User clicks logout OR admin revokes a specific session |
| **Outcome** | `sessions.status → revoked` · Refresh token invalidated immediately |

### Overview

There are three sub-flows: self-logout (single session), admin single-session revoke, and admin all-sessions revoke. The access JWT remains technically valid until its 15-min TTL — but the refresh token is immediately invalid, so the user cannot get a new access token.

### Tables Affected

`identity.sessions` · `identity.audit_log`

### Sub-flow A — Self Logout (Single Session)

**`DELETE /auth/session`** — Revoke the caller's own current session. Requires Bearer token.

**Request:**
```
Authorization: Bearer <token>
// No body needed — session derived from JWT sid claim
```

**Response:**
```json
{
  "message": "Session revoked. Please log in again."
}
```

**HTTP Codes:** `200 OK` · `401 invalid token` · `404 session not found`

### Sub-flow B — Admin Revoke Specific Session

**`DELETE /auth/sessions/{session_id}`** — Force-revoke any session belonging to a user in the admin's tenant. Requires `tenant.admin` permission.

**Request:**
```
Authorization: Bearer <token>
X-Tenant-Id: acme-prod
```

**Response:**
```json
{
  "session_id": "session-uuid-target",
  "status": "revoked",
  "revoked_at": "2024-06-15T10:00:11Z"
}
```

**HTTP Codes:** `200 OK` · `403 no permission or session belongs to different tenant` · `404 session not found`

### Sub-flow C — Revoke All Other Sessions

**`DELETE /auth/sessions`** — Revoke ALL sessions for the current user EXCEPT the current one.

**Request:**
```
Authorization: Bearer <token>
```

**Response:**
```json
{
  "revoked_count": 3,
  "message": "3 sessions revoked"
}
```

**HTTP Codes:** `200 OK` · `401 invalid token`

### State Changes (All Sub-flows)

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.sessions.status` | `'active'` | `'revoked'` | `user.session_revoked` |
| `identity.sessions.revoked_at` | `NULL` | `now()` | — |
| `identity.audit_log` | — | new row inserted | `user.session_revoked` |

> ⚠️ The access JWT is **not** invalidated — it cannot be, because JWTs are stateless. It will expire naturally in ≤15 min. For high-security revocations, consider also setting a short-lived `'revoked_jwts'` cache keyed on `jti` or `sid`.

---

## J06 — Password Reset

| Field | Value |
|-------|-------|
| **Actor** | User who forgot their password (not logged in) |
| **Trigger** | User submits email → receives reset link → submits new password |
| **Outcome** | Password updated in Keycloak · All existing sessions revoked · Audit logged |

### Overview

Password reset is a 2-step flow. Step 1 sends a time-limited signed reset token to the user's email. Step 2 accepts the token and new password, updates Keycloak, and revokes all existing sessions to force re-authentication everywhere. The platform does **not** store the password — only Keycloak does.

### Tables Affected

`identity.users` · `identity.sessions` · `identity.audit_log`

### Step 1 — Request Reset Link

**`POST /auth/password/reset-request`** — Initiate password reset. Always returns `200` (never reveals if email exists).

**Request:**
```json
{
  "email": "alice@example.com"
}
```

**Response:**
```json
{
  "message": "If that email exists, a reset link has been sent."
}
```

**HTTP Codes:** `200 OK` (always — no `404` to prevent email enumeration)

### Step 2 — Submit New Password

**`POST /auth/password/reset`** — Submit the token from the email and set a new password.

**Request:**
```json
{
  "reset_token": "signed-jwt-reset-token",
  "new_password": "NewSecurePass456!"
}
```

**Response:**
```json
{
  "message": "Password updated. All sessions revoked. Please log in again.",
  "sessions_revoked": 2
}
```

**HTTP Codes:** `200 OK` · `400 token invalid or expired (10 min TTL)` · `422 password too weak`

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.users.updated_at` | (previous) | `now()` | `user.password_reset` |
| `identity.sessions.status` (ALL) | `'active'` | `'revoked'` (bulk) | `user.sessions_revoked` |
| `identity.sessions.revoked_at` | `NULL` | `now()` (bulk) | — |
| `identity.audit_log` | — | new row inserted | `user.password_reset` |

> ⚠️ The actual password hash lives only in Keycloak, not in the platform DB. The platform calls the Keycloak Admin API to set the new credential. If the Keycloak call succeeds but the session revocation fails, the Keycloak password change is **not** rolled back — an outbox task retries session revocation.

---

## J07 — Organization Upgrade (Individual → Organization)

| Field | Value |
|-------|-------|
| **Actor** | Individual org owner (tenant-admin of their default tenant) |
| **Trigger** | Owner submits org registration form with company name, slug, contacts |
| **Outcome** | Dedicated Keycloak realm created · `org_type = organization` · `keycloak_realm_ref` stored · org-owner role seeded |

### Overview

This is the most complex journey — it crosses Identity, Tenant, and Authorization domains. The user's `org_type` changes from `'individual'` to `'organization'`, a new Keycloak realm is provisioned, and the owner's role binding is updated. The slug is **permanent** after this point. An `OrganizationRegistrationRequest` record tracks the pipeline state.

### Tables Affected

`identity.identity_realms` · `identity.users` · `tenant.organizations` · `tenant.org_memberships` · `tenant.tenants` · `authz.roles` · `authz.user_roles` · `identity.audit_log`

### Step 1 — Submit Registration Request

**`POST /organizations/register`** — Submit org upgrade request. Requires Bearer token + existing individual org ownership.

**Request:**
```json
{
  "name": "Acme Corp",
  "slug": "acme-corp",
  "contact_name": "Alice Smith",
  "contact_email": "alice@acme.com",
  "country": "IN"
}
```

**Response:**
```json
{
  "request_id": "req-uuid-001",
  "status": "processing",
  "org_id": "org-uuid-acme",
  "estimated_ms": 15000
}
```

**HTTP Codes:** `202 Accepted` · `409 slug already taken` · `403 already an organization` · `422 invalid slug format`

### Step 2 — Poll Registration Status

**`GET /organizations/register/{request_id}`** — Poll the status of the async registration pipeline.

**Request:**
```
Authorization: Bearer <token>
```

**Response:**
```json
{
  "request_id": "req-uuid-001",
  "status": "completed",
  "org_id": "org-uuid-acme",
  "keycloak_realm_ref": "acme-corp",
  "realm_url": "acme-corp.auth.platform.io"
}
```

**HTTP Codes:** `200 OK` · `404 request not found` · `403 not the request owner`

### Internal Pipeline (OrganizationRegistrationRequest)

| Step | Domain | Action | DB Write |
|------|--------|--------|----------|
| 1 — validate | Tenant | Check slug unique, contact valid, user is individual org owner | `READ tenant.organizations WHERE slug=? must = 0 rows` |
| 2 — provision realm | Identity | Call Keycloak Admin API to create org realm `'acme-corp'` | `INSERT identity.identity_realms (realm_type='org', organization_id=...)` |
| 3 — update org record | Tenant | Set `org_type='organization'`, store `keycloak_realm_ref` | `UPDATE tenant.organizations SET org_type='organization', keycloak_realm_ref='acme-corp'` |
| 4 — seed default tenant | Tenant | Create `acme-corp-default` tenant under the new org | `INSERT tenant.tenants (slug='acme-corp-default', organization_id=...)` |
| 5 — seed roles | AuthZ | Create tenant-admin, resource-admin, viewer roles for new tenant | `INSERT authz.roles (3 rows, is_system=true, scope_id=new_tenant_id)` |
| 6 — assign org-owner | AuthZ | Grant alice the `tenant-admin` role in the new org-default tenant | `INSERT authz.user_roles (user_id=alice, role=tenant-admin, ...)` |
| 7 — emit events | Audit | Write `organization.registered` + `keycloak.realm.created` to audit log | `INSERT identity.audit_log (2 rows)` |

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `tenant.organizations.org_type` | `'individual'` | `'organization'` | `org.registered` |
| `tenant.organizations.keycloak_realm_ref` | `NULL` | `'acme-corp'` | — |
| `identity.identity_realms` | — | new row (`realm_type='org'`) | `keycloak.realm.created` |
| `authz.roles` | 3 rows (old tenant) | 3 new rows (new tenant) | `roles.seeded` |
| `authz.user_roles` | alice → old tenant | alice → tenant-admin in new tenant | `role_binding.created` |
| `identity.audit_log` | — | 2 new rows | `org.registered` |

> ⚠️ The slug is stored as `keycloak_realm_ref` permanently. There is no API to rename it after creation. If the Keycloak realm provisioning fails (step 2), the entire pipeline rolls back and the `request_id` shows `status='failed'`.

---

## J08 — Service Account Creation

| Field | Value |
|-------|-------|
| **Actor** | Tenant admin (human) |
| **Trigger** | Admin creates a robot user for CI/CD or scripting |
| **Outcome** | `ServiceAccount` row created · API key generated (shown once) · Roles assigned to SA in that tenant |

### Overview

Service accounts are non-human principals scoped to exactly one tenant. They authenticate via API key (not password). The API key is shown **once** at creation — only the bcrypt hash is stored. The SA can be granted roles just like a human user via `authz.user_roles` (`principal_type='service_account'`).

### Tables Affected

`identity.service_accounts` · `identity.api_keys` · `authz.user_roles` · `identity.audit_log`

### Step 1 — Create Service Account

**`POST /tenants/{tenant_id}/service-accounts`** — Create a new service account in the tenant. Requires `tenant.admin` permission.

**Request:**
```json
{
  "name": "sa-deploy-prod",
  "description": "CI/CD deployment bot for payments service",
  "initial_role": "resource-admin"
}
```

**Response:**
```json
{
  "service_account_id": "sa-uuid-001",
  "name": "sa-deploy-prod",
  "api_key": "ak_sc8fx2aa_FULL_KEY_HERE",
  "key_prefix": "ak_sc8fx2aa",
  "status": "active",
  "role_assigned": "resource-admin"
}
```

**HTTP Codes:** `201 Created` · `403 no tenant.admin permission` · `409 SA name already exists in this tenant` · `422 invalid name`

### Step 2 — Assign or Change SA Role

**`POST /tenants/{tenant_id}/service-accounts/{sa_id}/roles`** — Assign a role to the service account.

**Request:**
```json
{
  "role_id": "role-uuid-resource-admin",
  "justification": "Deploy pipeline needs resource create"
}
```

**Response:**
```json
{
  "user_role_id": "ur-uuid-001",
  "principal_type": "service_account",
  "role": "resource-admin",
  "scope": "tenant:acme-prod",
  "status": "active"
}
```

**HTTP Codes:** `201 Created` · `403 no tenant.admin permission` · `404 SA or role not found`

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.service_accounts` | — (row didn't exist) | `status='active'` | `service_account.created` |
| `identity.api_keys` | — (row didn't exist) | `key_hash` set, `status='active'` | `api_key.created` |
| `authz.user_roles` | — (row didn't exist) | `principal_type='service_account', status='active'` | `role_binding.created` |
| `identity.audit_log` | — | 2 new rows | `sa.created · role_binding.created` |

> ⚠️ The raw API key is generated using `crypto.randomBytes(32)`, prefixed with `'ak_'`, then bcrypt-hashed. The raw key is returned **once** in the creation response and then discarded. If the admin loses it, they must rotate (J09).

---

## J09 — API Key Rotation / Revocation

| Field | Value |
|-------|-------|
| **Actor** | Tenant admin or SA owner |
| **Trigger** | Key is compromised, expired, or needs routine rotation |
| **Outcome** | Old key revoked · New key generated (shown once) OR key permanently revoked |

### Tables Affected

`identity.api_keys` · `identity.audit_log`

### Sub-flow A — Rotate (Revoke + Issue New Key Atomically)

**`POST /tenants/{tenant_id}/service-accounts/{sa_id}/api-keys/rotate`** — Atomically revoke the existing key and issue a new one. Requires `tenant.admin`.

**Request:**
```json
{
  "reason": "Routine 90-day rotation"
}
```

**Response:**
```json
{
  "old_key_prefix": "ak_sc8fx2aa",
  "old_key_status": "revoked",
  "new_api_key": "ak_d4f91bcx_FULL_NEW_KEY",
  "new_key_prefix": "ak_d4f91bcx",
  "new_status": "active"
}
```

**HTTP Codes:** `200 OK` · `403 no tenant.admin permission` · `404 SA not found` · `409 no active key exists to rotate`

### Sub-flow B — Revoke Only (No Replacement)

**`DELETE /tenants/{tenant_id}/service-accounts/{sa_id}/api-keys/{key_id}`** — Permanently revoke an API key with no replacement. SA cannot authenticate until new key issued.

**Request:**
```json
{
  "reason": "Key believed compromised"
}
```

**Response:**
```json
{
  "key_id": "key-uuid-001",
  "key_prefix": "ak_sc8fx2aa",
  "status": "revoked",
  "revoked_at": "2024-06-15T10:00:00Z"
}
```

**HTTP Codes:** `200 OK` · `403 no permission` · `404 key not found` · `409 already revoked`

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `identity.api_keys.status` (old) | `'active'` | `'revoked'` | `api_key.revoked` |
| `identity.api_keys.revoked_at` | `NULL` | `now()` | — |
| `identity.api_keys` (new) | — (row didn't exist) | `status='active'` | `api_key.created` |
| `identity.api_keys.key_hash` | (old hash) | (new hash — rotated) | — |
| `identity.audit_log` | — | 1–2 new rows | `api_key.rotated` or `api_key.revoked` |

> ✅ Rotation is **atomic** — both old revoke and new key insert happen in one transaction. There is never a window where the SA has no key (rotation) or two active keys (creation). An SA can only have **ONE** active API key at a time.

---

## J10 — Role Assignment (Grant Access)

| Field | Value |
|-------|-------|
| **Actor** | Tenant admin (human with `tenant.admin` permission) |
| **Trigger** | Admin decides to give a user or SA a specific role in this tenant |
| **Outcome** | `authz.user_roles` row created (`status=active`) · Target user gains permissions immediately |

### Overview

Role assignment creates an `authz.user_roles` row linking a user (or SA) to a role at a specific scope. Because roles are resolved fresh from the DB on every API request, the target user gains the new permissions on their **very next API call** — no cache invalidation needed.

### Tables Affected

`authz.roles` · `authz.user_roles` · `authz.permissions` · `authz.role_permissions` · `identity.audit_log`

### API Call

**`POST /tenants/{tenant_id}/roles/{role_id}/bindings`** — Assign a role to a user or SA in this tenant. Requires `tenant.admin` permission.

**Request:**
```json
{
  "principal_id": "user-uuid-bob-001",
  "principal_type": "user",
  "expires_at": "2024-12-31T23:59:59Z",
  "justification": "Bob needs resource-admin for Q4 migration"
}
```

**Response:**
```json
{
  "binding_id": "ur-uuid-002",
  "user_id": "user-uuid-bob-001",
  "role": "resource-admin",
  "scope": "tenant:acme-prod",
  "status": "active",
  "granted_by": "user-uuid-alice-001",
  "granted_at": "2024-06-15T10:24:00Z",
  "expires_at": "2024-12-31T23:59:59Z"
}
```

**HTTP Codes:** `201 Created` · `403 caller lacks tenant.admin` · `404 user or role not found` · `409 binding already exists` · `422 role scope mismatch`

### Authorization Checks Inside the Handler

| Check | Query | Fail Response |
|-------|-------|---------------|
| Caller has `tenant.admin` | `authz.user_roles WHERE user_id=caller AND scope_id=tenant AND status='active'` + role includes `tenant.admin` | `403 — 'You do not have permission to assign roles'` |
| Target user exists | `identity.users WHERE id=principal_id` | `404 — 'User not found'` |
| Role exists in this tenant | `authz.roles WHERE id=role_id AND scope_id=tenant_id` | `404 — 'Role not found in this tenant'` |
| No duplicate binding | `authz.user_roles WHERE user_id=principal_id AND role_id=role_id AND scope_id=tenant_id AND status='active'` | `409 — 'User already has this role'` |
| Role scope matches | `roles.scope_type` must = `'tenant'` (not `'platform'`) | `422 — 'Cannot assign platform-scope role in tenant context'` |

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `authz.user_roles` | — (row didn't exist) | `status='active'` | `role_binding.created` |
| `authz.user_roles.granted_by` | — | caller `user_id` | — |
| `identity.audit_log` | — | new row inserted | `role_binding.created` |

### What Bob Can Do Immediately After This Call

| Permission | Granted via resource-admin? | Can Bob Do This Now? |
|------------|-----------------------------|----------------------|
| `resource.read` | Yes | ✅ Yes — on next API call |
| `resource.create` | Yes | ✅ Yes — on next API call |
| `resource.allocation.create` | Yes | ✅ Yes — on next API call |
| `resource.allocation.approve` | Yes | ✅ Yes — on next API call |
| `tenant.admin` | No — not in resource-admin | ❌ No |
| `audit.read` | No — not in resource-admin | ❌ No |
| `platform.admin` | No — wrong scope | ❌ No — ever |

> ✅ Permissions take effect on Bob's **very next API call**. No re-login needed. No token re-issue needed. The authorization evaluation query hits the DB fresh every time and sees the new `user_roles` row immediately.

---

## J11 — Role Revocation

| Field | Value |
|-------|-------|
| **Actor** | Tenant admin (human with `tenant.admin` permission) |
| **Trigger** | Admin removes a user's role — immediately deny their access |
| **Outcome** | `authz.user_roles.status → revoked` · Target user denied on their next API call |

### Overview

Revocation is the most security-critical journey. Because roles are resolved from the DB on every request, revocation is effective on the **very next API call** by the target user — even if their JWT has 14 minutes left. The `user_roles` row is **not deleted** — it is kept with `status='revoked'` so audit history can answer `'who had what role when'`.

### Tables Affected

`authz.user_roles` · `identity.audit_log`

### API Call

**`DELETE /tenants/{tenant_id}/roles/{role_id}/bindings/{binding_id}`** — Revoke a role binding. Requires `tenant.admin`. Binding row is kept with `status=revoked`.

**Request:**
```json
{
  "reason": "Carol has left the team as of today"
}
```

**Response:**
```json
{
  "binding_id": "ur-uuid-carol",
  "status": "revoked",
  "revoked_by": "user-uuid-alice",
  "revoked_at": "2024-06-15T10:00:11Z",
  "effective": "immediately"
}
```

**HTTP Codes:** `200 OK` · `403 caller lacks tenant.admin` · `404 binding not found` · `409 binding already revoked`

### State Changes

| Table / Column | Before | After / Created | Audit Event |
|----------------|--------|-----------------|-------------|
| `authz.user_roles.status` | `'active'` | `'revoked'` | `role_binding.revoked` |
| `authz.user_roles.revoked_by` | `NULL` | caller `user_id` | — |
| `authz.user_roles.revoked_at` | `NULL` | `now()` | — |
| `identity.audit_log` | — | new row inserted | `role_binding.revoked` |

### Timeline — Carol's 10:00 AM Revocation

| Time | Event | Carol's Access |
|------|-------|----------------|
| 09:58 AM | Carol calls `DELETE /resources/cluster-1` (JWT valid, role active) | ✅ ALLOWED — `user_roles` shows active row → permissions granted |
| 10:00 AM | Alice calls `DELETE /roles/{id}/bindings/carol-binding` | Role revoked — `user_roles.status = 'revoked'` |
| 10:01 AM | Carol calls `POST /allocations` (JWT still valid — expires 10:15) | ❌ DENIED 403 — authz query finds 0 active rows for Carol |
| 10:02 AM | Carol tries to refresh her access token | ❌ Refresh still works (session not revoked) but next check fails |
| 10:15 AM | Carol's JWT expires naturally | ❌ Token also expired — cannot make requests without re-login |

### Why the `user_roles` Row Is Never Deleted

| If Row Were Deleted | If Row Is Kept (`status=revoked`) |
|---------------------|-----------------------------------|
| Audit query: `'Did Carol have tenant-admin at 09:58?'` → impossible to answer | Audit query finds row with `granted_at=08:00, revoked_at=10:00` → clear answer |
| Cannot show who granted and who revoked the access | `granted_by + granted_at + revoked_by + revoked_at` all preserved |
| Compliance reports miss historical access periods | Full access timeline reconstructable from `user_roles` alone |
| Re-granting appears identical to first grant — no history | Each grant+revoke cycle creates a new row — full version history |

> ⚠️ **Never** call `DELETE` on `authz.user_roles` rows. The API handler must be hardcoded to `UPDATE status='revoked'`. Any raw SQL delete is a compliance violation.

---

## Cross-Journey State Summary

Which table rows are created or mutated in each journey.

| Table | J1 Reg | J2 Verify | J3 Login | J4 Refresh | J5 Logout | J6 PwReset | J7 OrgUpgrade | J8 SA | J9 KeyRotate | J10 Grant | J11 Revoke |
|-------|--------|-----------|----------|------------|-----------|------------|---------------|-------|--------------|-----------|------------|
| `identity.users` | INSERT | UPDATE | READ | — | — | READ | READ | — | — | — | — |
| `identity.credentials` | INSERT | — | READ | — | — | — | — | — | — | — | — |
| `identity.sessions` | — | — | INSERT | UPDATE | UPDATE | UPDATE (bulk) | — | — | — | — | — |
| `identity.identity_realms` | READ | — | READ | — | — | — | INSERT | — | — | — | — |
| `identity.service_accounts` | — | — | — | — | — | — | — | INSERT | READ | — | — |
| `identity.api_keys` | — | — | — | — | — | — | — | INSERT | UPDATE + INSERT | — | — |
| `identity.audit_log` | INSERT | INSERT | INSERT | — | INSERT | INSERT | INSERT ×2 | INSERT ×2 | INSERT | INSERT | INSERT |
| `tenant.organizations` | INSERT | — | — | — | — | — | UPDATE | — | — | — | — |
| `tenant.org_memberships` | INSERT | — | — | — | — | — | — | — | — | — | — |
| `tenant.tenants` | INSERT | — | — | — | — | — | INSERT | — | — | — | — |
| `authz.roles` | INSERT ×3 | — | — | — | — | — | INSERT ×3 | — | — | READ | READ |
| `authz.role_permissions` | READ | — | READ | — | — | — | READ | — | — | READ | READ |
| `authz.user_roles` | INSERT | — | READ | READ | — | — | INSERT | INSERT | — | INSERT | UPDATE |
| `authz.permissions` | READ | — | READ | — | — | — | READ | — | — | READ | READ |

> `INSERT` = new row created · `UPDATE` = existing row modified · `READ` = queried only · `—` = table not touched in this journey

---

*End of Identity & Authorization User Journey Reference — TenantPlatform v2*
