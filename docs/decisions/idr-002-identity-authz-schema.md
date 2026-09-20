# IDR-002: Identity & Authorization schema (principals-centric)

**Status:** Accepted  
**Date:** 2026-09-07  
**Related:** Prompt 2 schema evolution; migration `0004_identity_authz_principals_schema`

## Decision

Evolve Phase 1 `identity.*` / `authz.*` tables toward a principals-centric model with **explicit** `tenant_id` XOR `operator_org_id` scope columns. Do not use polymorphic RBAC `scope_id` on roles or role bindings.

## Constraints (summary)

| Area | Rule |
|------|------|
| IDs | UUID PKs; `timestamptz` timestamps |
| Secrets | Never store passwords, refresh tokens, or raw API keys in platform DB |
| Principals | `identity.principals` is the AuthZ subject; users and service accounts link via `principal_id` |
| Credentials | Unique `(identity_realm_id, keycloak_subject)`; FK to principals + realms |
| API keys | Hash + prefix only; at most one active key per SA; unique active prefix |
| Roles | XOR: tenant scope ⇒ `tenant_id` set / `operator_org_id` null; platform ⇒ inverse |
| Bindings | `authz.principal_roles` soft-revoke only (`status` / `revoked_at`); never hard-delete for audit |
| Audit | `authz.authorization_audit_log` append-only; explicit nullable scope columns |

## Migration notes

- Upgrade is data-preserving where possible (backfill principals, map credentials, rename `user_roles` → `principal_roles`).
- **Breakage:** `sessions.refresh_token_hash` dropped. Phase 1 J4 refresh returns 403 until Prompt 3 (Keycloak JWT dual-path).
- Downgrade recreates `scope_id` / `user_roles`; cannot restore dropped refresh hashes.

## Non-goals

Keycloak JWT adapter (Prompt 3), resource vertical slice (Prompt 6).

`AuthorizationService.authorize` (Prompt 4) and permission catalog seed (Prompt 5 / migration `0006`) are implemented under `src/authz/`.
