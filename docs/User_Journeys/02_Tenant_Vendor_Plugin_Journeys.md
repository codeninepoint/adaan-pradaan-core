# Tenant, Vendor & Plugin — Complete User Journey Reference
### 26 Journeys · Every API · Every Table · Every State Change
**Multi-Tenant Cloud Platform — Phase 2** (continues numbering from Journey 1: Identity & Authorization, J1–J11)

> Companion document to `01_Identity_Auth_Journeys` (J1–J11). This document covers everything that happens **after** a user has registered, verified, logged in, and optionally upgraded to an Organization (J7). It maps 1:1 onto the 28 screens in the "Tenant, Vendor and Plugin UI Screens" file: **Tenant Journeys, Organization, Vendor Registration, Plugin Publishing, Product & Marketplace, Platform Governance.**

## Journey Index

| # | Journey | Actor | Key Tables | UI Screen(s) |
|---|---|---|---|---|
| J12 | Tenant Creation | Org owner / tenant-admin | `tenant.tenants`, `tenant.projects`, `authz.roles`, `authz.user_roles`, `identity.audit_log` | t_create |
| J13 | Project Creation | Tenant-admin / resource-admin | `tenant.projects`, `tenant.tenants`, `identity.audit_log` | t_project |
| J14 | Tenant Member Management (Invite / Remove / Change Role) | Tenant-admin | `tenant.tenant_memberships`, `identity.users`, `authz.user_roles`, `identity.audit_log` | t_members |
| J15 | Tenant Settings Update | Tenant-admin | `tenant.tenants`, `identity.audit_log` | t_settings |
| J16 | Tenant Onboarding Journey (guided checklist) | Tenant-admin | `tenant.onboarding_checklists`, `tenant.tenants` | t_onboard |
| J17 | Organization Overview (read) | Any org member | `tenant.organizations`, `tenant.tenants`, `tenant.org_memberships` (read-only) | o_overview |
| J18 | Realm Provisioning Detail (read/retry) | Org owner | `identity.identity_realms`, `tenant.organizations` | o_realm |
| J19 | Organization Member Management | Org owner / tenant-admin | `tenant.org_memberships`, `identity.users`, `authz.user_roles`, `identity.audit_log` | o_members |
| J20 | Become a Vendor (eligibility check) | Org owner | `tenant.organizations`, `vendor.profiles` (read) | v_intro |
| J21 | Vendor Registration | Org owner | `vendor.profiles`, `tenant.organizations`, `identity.audit_log` | v_register |
| J22 | Vendor Verification (KYC review) | Platform ops / vendor | `vendor.verifications`, `vendor.profiles`, `identity.audit_log` | v_verify |
| J23 | Vendor Portal (operational home, read) | Vendor admin | `vendor.profiles`, `marketplace.products`, `marketplace.offerings`, `marketplace.installations` (read) | v_portal |
| J24 | Plugin Registration | Vendor admin | `marketplace.plugins`, `identity.audit_log` | p_register |
| J25 | Plugin Version Submission | Vendor admin | `marketplace.plugin_versions`, `identity.audit_log` | p_version |
| J26 | Plugin Governance Review (decision) | Platform governance admin | `marketplace.plugin_versions`, `identity.audit_log` | p_govern (write half — see J36) |
| J27 | Plugin Capability Declaration | Vendor admin | `marketplace.plugin_capabilities`, `marketplace.plugin_versions`, `identity.audit_log` | p_caps |
| J28 | Plugin Version History (read) | Vendor admin / governance | `marketplace.plugin_versions` (read-only) | p_versions |
| J29 | Create Product | Vendor admin | `marketplace.products`, `identity.audit_log` | m_product |
| J30 | Create Offering (pricing/plan) | Vendor admin | `marketplace.offerings`, `marketplace.products`, `identity.audit_log` | m_offering |
| J31 | Marketplace Catalog Browse (read) | Tenant-admin (buyer) | `marketplace.offerings`, `marketplace.products` (read-only) | m_catalog |
| J32 | Install Offering | Tenant-admin (buyer) | `marketplace.installations`, `marketplace.entitlements`, `marketplace.offerings`, `identity.audit_log` | m_install |
| J33 | My Entitlements (read) | Tenant-admin | `marketplace.entitlements` (read-only) | m_entitle |
| J34 | Provision Service (async) | System (outbox worker) | `marketplace.service_instances`, `marketplace.installations`, `identity.audit_log` | m_provision |
| J35 | Review Plugins Queue (read + claim) | Platform governance admin | `marketplace.plugin_versions` | g_plugins |
| J36 | Approve / Reject Plugin Version | Platform governance admin | `marketplace.plugin_versions`, `marketplace.plugins`, `identity.audit_log` | g_approve |
| J37 | Vendor Directory & Suspension | Platform governance admin | `vendor.profiles`, `marketplace.offerings`, `identity.audit_log` | g_vendors |

**Column colour coding (kept consistent with Journey 1):** INDIGO = `identity.*` · TEAL = `tenant.*` · CORAL = `vendor.*` · PURPLE = `marketplace.*` · AMBER = PK / state column · RED = `authz.*` writes.

---

## Journey 12 — Tenant Creation

**Actor:** Org owner or existing tenant-admin
**Trigger:** User clicks "Create New Tenant" to spin up an additional environment (e.g. `acme-staging` alongside `acme-prod`) under the same organization
**Outcome:** New `tenant.tenants` row (`status='active'`) · default project seeded · caller granted `tenant-admin` in the new tenant

### API
`POST /organizations/{org_id}/tenants`
Requires Bearer token + `org.admin` or existing `tenant-admin` in any sibling tenant of the org.

```json
// Input
{ "name": "Acme Staging", "slug": "acme-staging", "region": "ap-south-1", "environment": "staging" }
```
```json
// Output
{ "tenant_id": "ten-uuid-002", "slug": "acme-staging", "status": "active",
  "org_id": "org-uuid-acme", "default_project_id": "proj-uuid-002" }
```
`201 Created` · `409` slug already taken within org · `403` caller lacks org.admin · `422` invalid slug/region

### Internal steps
| Step | Domain | Action | DB Write |
|---|---|---|---|
| 1 | Tenant | Validate slug unique **within org** | `SELECT tenant.tenants WHERE org_id=? AND slug=?` → 0 rows |
| 2 | Tenant | INSERT tenant row | `status='active'`, `org_id`, `region`, `environment` |
| 3 | Tenant | Seed default project | `INSERT tenant.projects (name='default-project', tenant_id=new)` |
| 4 | AuthZ | Seed tenant-scoped roles | `INSERT authz.roles` (tenant-admin, resource-admin, viewer; `scope_id=new_tenant`) |
| 5 | AuthZ | Bind caller as tenant-admin | `INSERT authz.user_roles` (caller → tenant-admin, new tenant) |
| 6 | Audit | Log | `tenant.created` |

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `tenant.tenants` | — (row didn't exist) | `status='active'` | `tenant.created` |
| `tenant.projects` | — | `default-project` row | `project.created` |
| `authz.roles` | — | 3 rows, `is_system=true` | `roles.seeded` |
| `authz.user_roles` | — | caller → tenant-admin (new tenant) | `role_binding.created` |

> Tenant quota check: org plan may cap max tenants (e.g. free tier = 1). Enforce at step 1 with `409 — 'tenant quota exceeded for this plan'`.

---

## Journey 13 — Project Creation

**Actor:** Tenant-admin or resource-admin
**Trigger:** User clicks "Create Project" inside a tenant
**Outcome:** New `tenant.projects` row scoped to the tenant · optional resource quota attached

### API
`POST /tenants/{tenant_id}/projects`
Requires `tenant.admin` or `resource.create` permission.

```json
// Input
{ "name": "payments-service", "description": "Core payments microservice project", "quota_cpu": 16, "quota_memory_gb": 64 }
```
```json
// Output
{ "project_id": "proj-uuid-003", "name": "payments-service", "tenant_id": "ten-uuid-001", "status": "active" }
```
`201 Created` · `403` no `resource.create` in this tenant · `409` project name already exists in tenant

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `tenant.projects` | — | `status='active'` | `project.created` |
| `identity.audit_log` | — | new row | `project.created` |

> Note: this is the same permission model surfaced in Journey 10 (Role Assignment) — `resource.create` is one of the permissions granted by the `resource-admin` role.

---

## Journey 14 — Tenant Member Management (Invite / Remove / Change Role)

**Actor:** Tenant-admin
**Trigger:** Admin invites a teammate to a specific tenant (narrower scope than an org-level invite — see J19), or changes/removes an existing member's tenant role
**Outcome:** Invitee gains a role binding scoped to **this tenant only** (not the whole org)

### Sub-flow A — Invite existing org member into a tenant
`POST /tenants/{tenant_id}/members`
```json
// Input
{ "user_id": "user-uuid-bob", "role": "resource-admin" }
```
```json
// Output
{ "membership_id": "tm-uuid-001", "tenant_id": "ten-uuid-001", "user_id": "user-uuid-bob",
  "role": "resource-admin", "status": "active" }
```
`201 Created` · `403` caller lacks `tenant.admin` · `404` user not found or not an org member · `409` already a member of this tenant

### Sub-flow B — Remove member from tenant
`DELETE /tenants/{tenant_id}/members/{user_id}`
```json
// Output
{ "user_id": "user-uuid-bob", "tenant_id": "ten-uuid-001", "status": "removed" }
```
`200 OK` · `403` no permission · `404` not a member · `409` cannot remove the last tenant-admin

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `tenant.tenant_memberships.status` | — (row didn't exist) | `'active'` | `tenant_member.added` |
| `authz.user_roles` | — | new row, scope=tenant | `role_binding.created` |
| `tenant.tenant_memberships.status` (removal) | `'active'` | `'removed'` | `tenant_member.removed` |
| `authz.user_roles.status` (removal) | `'active'` | `'revoked'` | `role_binding.revoked` |

> Guardrail (mirrors J11): the removal handler must reject with `409` if it would leave the tenant with zero active `tenant-admin` bindings.

---

## Journey 15 — Tenant Settings Update

**Actor:** Tenant-admin
**Trigger:** Admin edits name, region, environment tag, or feature flags on the tenant settings screen
**Outcome:** `tenant.tenants` row updated · audit trail of who changed what

### API
`PATCH /tenants/{tenant_id}/settings`
```json
// Input
{ "display_name": "Acme Production (Mumbai)", "feature_flags": { "beta_billing_v2": true } }
```
```json
// Output
{ "tenant_id": "ten-uuid-001", "display_name": "Acme Production (Mumbai)",
  "feature_flags": { "beta_billing_v2": true }, "updated_at": "2024-06-15T11:00:00Z" }
```
`200 OK` · `403` no `tenant.admin` · `422` invalid feature flag key

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `tenant.tenants.display_name` | old value | new value | `tenant.settings_updated` |
| `tenant.tenants.feature_flags` | old JSON | merged JSON | `tenant.settings_updated` |
| `tenant.tenants.updated_at` | previous | now() | — |

> `slug` and `region` are **immutable** after creation (same permanence rule as `keycloak_realm_ref` in J7) — reject with `422` if present in the patch body.

---

## Journey 16 — Tenant Onboarding Journey (Guided Checklist)

**Actor:** Tenant-admin (just created a tenant)
**Trigger:** First visit to a new tenant — platform shows a checklist: invite team → create project → generate API key → install first offering
**Outcome:** `tenant.onboarding_checklists` row tracks completion; each checklist item is derived from **read** queries against other domains (no separate writes except marking steps seen/dismissed)

### API
`GET /tenants/{tenant_id}/onboarding`
```json
// Output
{ "tenant_id": "ten-uuid-001",
  "steps": [
    { "key": "invite_team",   "done": false },
    { "key": "create_project","done": true  },
    { "key": "create_api_key","done": false },
    { "key": "install_offering","done": false }
  ], "percent_complete": 25 }
```

`POST /tenants/{tenant_id}/onboarding/dismiss` — hides the checklist card permanently.
```json
{ "dismissed": true }
```

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `tenant.onboarding_checklists.dismissed` | `false` | `true` | — |

Each `done` flag is computed live (e.g. `done:create_project` = `EXISTS(SELECT 1 FROM tenant.projects WHERE tenant_id=? AND id != default_project_id)`), **not** stored redundantly — this avoids drift between the checklist and the real domain state, the same "resolve fresh every time" philosophy used for permissions in J10/J11.

---

## Journey 17 — Organization Overview (Read)

**Actor:** Any org member
**Trigger:** Visiting the Org Overview screen
**Outcome:** Read-only aggregation — no writes

### API
`GET /organizations/{org_id}/overview`
```json
// Output
{ "org_id": "org-uuid-acme", "name": "Acme Corp", "org_type": "organization",
  "participation": "consumer_and_vendor", "tenant_count": 2, "member_count": 6,
  "keycloak_realm_ref": "acme-corp" }
```
`200 OK` · `403` caller not an org member

**Tables read only:** `tenant.organizations`, `tenant.tenants` (count), `tenant.org_memberships` (count). No state changes — included here purely because it is a distinct screen/endpoint, matching the "view journeys" convention used for `o_overview`, `v_portal`.

---

## Journey 18 — Realm Provisioning Detail (Read / Retry)

**Actor:** Org owner
**Trigger:** Viewing realm status after J7, or retrying a failed provisioning pipeline
**Outcome:** Shows current `identity.identity_realms` state; if `status='failed'`, exposes a retry action

### API
`GET /organizations/{org_id}/realm`
```json
// Output
{ "org_id": "org-uuid-acme", "keycloak_realm_ref": "acme-corp",
  "realm_url": "acme-corp.auth.platform.io", "status": "active" }
```

`POST /organizations/{org_id}/realm/retry` — only valid when `status='failed'`. Re-runs pipeline step 2 from J7.
```json
{ "request_id": "req-uuid-002", "status": "processing" }
```
`202 Accepted` · `409` realm already active — nothing to retry

This journey is the **read/retry half** of J7's async pipeline — no new tables, reuses `identity.identity_realms` and the `OrganizationRegistrationRequest` pipeline defined in J7.

---

## Journey 19 — Organization Member Management

**Actor:** Org owner or tenant-admin with `org.admin`
**Trigger:** Inviting a new person to the **organization** (broader than J14's tenant-scoped invite) — they land with no tenant access until separately added via J14
**Outcome:** `tenant.org_memberships` row created with `role='member'|'owner'`

### API
`POST /organizations/{org_id}/members`
```json
// Input
{ "email": "carol@acme.com", "org_role": "member" }
```
```json
// Output
{ "invite_id": "inv-uuid-001", "email": "carol@acme.com", "org_role": "member", "status": "invited" }
```
`201 Created` · `403` no `org.admin` · `409` already invited or already a member

`DELETE /organizations/{org_id}/members/{user_id}` — removes org-level membership; cascades to remove all tenant-scoped role bindings for that user within this org's tenants.
```json
{ "user_id": "user-uuid-carol", "status": "removed", "tenant_bindings_revoked": 2 }
```

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `tenant.org_memberships.status` | — | `'invited'` → `'active'` (on accept) | `org_member.invited` / `org_member.joined` |
| `authz.user_roles` (cascade on removal) | `'active'` (N rows) | `'revoked'` (N rows) | `role_binding.revoked` |

---

## Journey 20 — Become a Vendor (Eligibility Check)

**Actor:** Org owner
**Trigger:** Clicking "Become a Vendor" — an informational screen with an eligibility check before the real registration form (J21)
**Outcome:** Read-only — tells the user whether they're eligible and what's required

### API
`GET /organizations/{org_id}/vendor-eligibility`
```json
// Output
{ "eligible": true, "reasons": [], "requirements": ["business_registration_doc", "bank_account", "tax_id"] }
```
If not eligible (e.g. still `org_type='individual'`):
```json
{ "eligible": false, "reasons": ["Must complete Organization Upgrade (Journey 7) first"], "requirements": [] }
```

No writes — this journey exists purely to gate entry into J21.

---

## Journey 21 — Vendor Registration

**Actor:** Org owner (of an org already provisioned via J7)
**Trigger:** Submitting the vendor registration form (business details, payout info, tax ID)
**Outcome:** `vendor.profiles` row created (`status='pending_verification'`) · `tenant.organizations.participation` updated to `consumer_and_vendor` · verification request auto-created (feeds J22)

### API
`POST /organizations/{org_id}/vendor/register`
```json
// Input
{ "legal_name": "Acme Corp Pvt Ltd", "tax_id": "27AAAAA0000A1Z5",
  "payout_bank_account": "XXXXXXXX1234", "contact_email": "vendor-ops@acme.com",
  "business_doc_url": "https://uploads.platform.io/docs/acme-reg.pdf" }
```
```json
// Output
{ "vendor_id": "vendor-uuid-001", "org_id": "org-uuid-acme", "status": "pending_verification",
  "verification_id": "ver-uuid-001" }
```
`202 Accepted` · `409` org already has a vendor profile · `422` missing required document

### Internal steps
| Step | Domain | Action | DB Write |
|---|---|---|---|
| 1 | Vendor | Validate org is `org_type='organization'` | READ `tenant.organizations` |
| 2 | Vendor | INSERT vendor profile | `status='pending_verification'` |
| 3 | Tenant | Update participation | `UPDATE tenant.organizations SET participation='consumer_and_vendor'` |
| 4 | Vendor | Create verification request | `INSERT vendor.verifications (status='queued')` |
| 5 | Audit | Log | `vendor.registered` |

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `vendor.profiles.status` | — | `'pending_verification'` | `vendor.registered` |
| `tenant.organizations.participation` | `'consumer'` | `'consumer_and_vendor'` | `org.participation_updated` |
| `vendor.verifications.status` | — | `'queued'` | `vendor.verification_requested` |

---

## Journey 22 — Vendor Verification (KYC Review)

**Actor:** Platform ops (reviewer) — vendor can view status read-only
**Trigger:** Verification request queued by J21; ops reviewer approves, rejects, or requests more info
**Outcome:** `vendor.profiles.status` → `verified` or `rejected` · vendor notified

### API — vendor-facing (read)
`GET /vendors/{vendor_id}/verification`
```json
{ "vendor_id": "vendor-uuid-001", "status": "pending_verification", "submitted_at": "2024-06-15T09:00:00Z" }
```

### API — ops-facing (write)
`POST /admin/vendor-verifications/{verification_id}/decision`
Requires `platform.admin` (or `governance.review` permission).
```json
// Input
{ "decision": "approved", "notes": "Business docs and tax ID confirmed against registrar." }
```
```json
// Output
{ "verification_id": "ver-uuid-001", "vendor_id": "vendor-uuid-001", "status": "approved",
  "decided_by": "user-uuid-ops-1", "decided_at": "2024-06-16T08:00:00Z" }
```
`200 OK` · `403` no `governance.review` · `404` verification not found · `409` already decided

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `vendor.verifications.status` | `'queued'` | `'approved'` / `'rejected'` | `vendor.verification_decided` |
| `vendor.profiles.status` | `'pending_verification'` | `'verified'` / `'rejected'` | `vendor.status_changed` |

> On rejection, `tenant.organizations.participation` is rolled back to `'consumer'` — a rejected vendor is not a partial vendor.

---

## Journey 23 — Vendor Portal (Operational Home, Read)

**Actor:** Vendor admin
**Trigger:** Landing on the Vendor Portal after verification
**Outcome:** Read-only dashboard aggregating the vendor's products, offerings, and installs

### API
`GET /vendors/{vendor_id}/portal`
```json
{ "vendor_id": "vendor-uuid-001", "status": "verified",
  "product_count": 3, "offering_count": 5, "active_installs": 42, "pending_plugin_reviews": 1 }
```
`200 OK` · `403` caller is not this vendor's admin

**Tables read only:** `vendor.profiles`, `marketplace.products`, `marketplace.offerings`, `marketplace.installations`, `marketplace.plugin_versions` (count where `status='pending_review'`). No writes.

---

## Journey 24 — Plugin Registration

**Actor:** Vendor admin (vendor must be `status='verified'`)
**Trigger:** Submitting "Register Plugin" form — creates the plugin shell before any version exists
**Outcome:** `marketplace.plugins` row created (`status='draft'`)

### API
`POST /vendors/{vendor_id}/plugins`
```json
// Input
{ "name": "Acme Fraud Scoring", "slug": "acme-fraud-scoring", "category": "risk_management",
  "short_description": "Real-time transaction risk scoring plugin." }
```
```json
// Output
{ "plugin_id": "plugin-uuid-001", "slug": "acme-fraud-scoring", "status": "draft", "vendor_id": "vendor-uuid-001" }
```
`201 Created` · `403` vendor not verified · `409` slug taken

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.plugins.status` | — | `'draft'` | `plugin.registered` |

---

## Journey 25 — Plugin Version Submission

**Actor:** Vendor admin
**Trigger:** Submitting a build (artifact URL / container digest) as a new version for governance review
**Outcome:** `marketplace.plugin_versions` row created (`status='pending_review'`) · feeds J35/J36 queue

### API
`POST /plugins/{plugin_id}/versions`
```json
// Input
{ "version": "1.0.0", "artifact_url": "oci://registry.platform.io/acme/fraud-scoring:1.0.0",
  "changelog": "Initial release.", "sbom_url": "https://uploads.platform.io/sbom/acme-1.0.0.json" }
```
```json
// Output
{ "version_id": "pv-uuid-001", "plugin_id": "plugin-uuid-001", "version": "1.0.0", "status": "pending_review" }
```
`201 Created` · `409` version string already submitted for this plugin · `422` missing SBOM (required for governance scan)

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.plugin_versions.status` | — | `'pending_review'` | `plugin_version.submitted` |
| `identity.audit_log` | — | new row | `plugin_version.submitted` |

> Submission triggers an outbox event (`type='scan_plugin_artifact'`) — mirrors the outbox pattern used for verification emails in J1.

---

## Journey 26 — Plugin Governance Review (Reviewer-Side Detail View)

**Actor:** Platform governance admin
**Trigger:** Opening a specific pending version from the queue (J35) to inspect diffs, capabilities requested (J27), and scan results before deciding (decision itself is J36)
**Outcome:** Read-heavy detail screen; only write is an optional "add reviewer note" / "request changes" action, distinct from the final approve/reject

### API
`GET /plugins/versions/{version_id}/review`
```json
{ "version_id": "pv-uuid-001", "plugin": "acme-fraud-scoring", "version": "1.0.0",
  "scan_status": "passed", "requested_capabilities": ["transactions.read", "webhooks.publish"],
  "sbom_url": "https://uploads.platform.io/sbom/acme-1.0.0.json" }
```

`POST /plugins/versions/{version_id}/request-changes`
```json
// Input
{ "notes": "Please justify the transactions.read scope — narrow it to a single project if possible." }
```
```json
{ "version_id": "pv-uuid-001", "status": "changes_requested" }
```
`200 OK` · `403` no `governance.review` · `409` not currently `pending_review`

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.plugin_versions.status` | `'pending_review'` | `'changes_requested'` | `plugin_version.changes_requested` |

---

## Journey 27 — Plugin Capability Declaration

**Actor:** Vendor admin
**Trigger:** Declaring which platform scopes/permissions the plugin needs (shown to governance in J26, and to the installing tenant in J32)
**Outcome:** `marketplace.plugin_capabilities` rows attached to a specific plugin version

### API
`PUT /plugins/versions/{version_id}/capabilities`
```json
// Input
{ "capabilities": [
    { "scope": "transactions.read", "justification": "Score transactions in real time" },
    { "scope": "webhooks.publish", "justification": "Emit fraud-score-updated events" }
  ] }
```
```json
// Output
{ "version_id": "pv-uuid-001", "capability_count": 2 }
```
`200 OK` · `403` caller is not this plugin's vendor · `409` version already approved — capabilities are frozen post-approval (must submit a new version to change scopes)

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.plugin_capabilities` | — (rows didn't exist) | N rows created | `plugin_capabilities.declared` |

---

## Journey 28 — Plugin Version History (Read)

**Actor:** Vendor admin / governance admin
**Trigger:** Viewing the full timeline of versions for a plugin
**Outcome:** Read-only — no writes

### API
`GET /plugins/{plugin_id}/versions`
```json
{ "plugin_id": "plugin-uuid-001",
  "versions": [
    { "version": "1.0.0", "status": "approved", "submitted_at": "…", "decided_at": "…" },
    { "version": "0.9.0-beta", "status": "rejected", "submitted_at": "…", "decided_at": "…" }
  ] }
```

Mirrors the "never delete, always append a new row + keep status history" philosophy from J11 (role revocation) — a plugin version is never deleted, only superseded.

---

## Journey 29 — Create Product

**Actor:** Vendor admin
**Trigger:** Creating a sellable product entity (the commercial wrapper around one or more plugins/services)
**Outcome:** `marketplace.products` row (`status='draft'`)

### API
`POST /vendors/{vendor_id}/products`
```json
// Input
{ "name": "Fraud Scoring Suite", "description": "Real-time and batch fraud scoring for payments platforms.",
  "plugin_id": "plugin-uuid-001" }
```
```json
// Output
{ "product_id": "prod-uuid-001", "name": "Fraud Scoring Suite", "status": "draft" }
```
`201 Created` · `403` vendor not verified · `404` plugin not found or not owned by vendor

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.products.status` | — | `'draft'` | `product.created` |

---

## Journey 30 — Create Offering (Pricing / Plan)

**Actor:** Vendor admin
**Trigger:** Attaching a pricing plan (tier, billing period, usage limits) to a product before it can be listed
**Outcome:** `marketplace.offerings` row (`status='draft'`, later published)

### API
`POST /products/{product_id}/offerings`
```json
// Input
{ "plan_name": "Pro", "billing_period": "monthly", "price_usd": 499,
  "included_transactions": 100000, "overage_price_per_1k": 2.5 }
```
```json
// Output
{ "offering_id": "off-uuid-001", "product_id": "prod-uuid-001", "plan_name": "Pro", "status": "draft" }
```

`POST /offerings/{offering_id}/publish` — moves `status` from `draft` to `published`, making it visible in J31's catalog.
```json
{ "offering_id": "off-uuid-001", "status": "published" }
```
`200 OK` · `409` product's plugin version not yet `approved` (cannot publish an offering backed by an unapproved plugin — links back to J36)

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.offerings.status` | — | `'draft'` | `offering.created` |
| `marketplace.offerings.status` (publish) | `'draft'` | `'published'` | `offering.published` |

---

## Journey 31 — Marketplace Catalog Browse (Read)

**Actor:** Tenant-admin acting as a buyer
**Trigger:** Browsing the marketplace catalog
**Outcome:** Read-only, paginated, filterable

### API
`GET /marketplace/catalog?category=risk_management&q=fraud`
```json
{ "results": [
    { "offering_id": "off-uuid-001", "product_name": "Fraud Scoring Suite", "vendor": "Acme Corp",
      "plan_name": "Pro", "price_usd": 499, "billing_period": "monthly" }
  ], "page": 1, "total": 1 }
```
`200 OK` — no auth required to browse; auth required only to install (J32).

**Tables read only:** `marketplace.offerings WHERE status='published'`, joined to `marketplace.products`, `vendor.profiles`.

---

## Journey 32 — Install Offering

**Actor:** Tenant-admin
**Trigger:** Clicking "Install" on a catalog offering for a specific tenant/project
**Outcome:** `marketplace.installations` row created · `marketplace.entitlements` row granted · async provisioning kicked off (J34)

### API
`POST /tenants/{tenant_id}/installations`
```json
// Input
{ "offering_id": "off-uuid-001", "project_id": "proj-uuid-002",
  "accepted_capabilities": ["transactions.read", "webhooks.publish"] }
```
```json
// Output
{ "installation_id": "inst-uuid-001", "offering_id": "off-uuid-001", "tenant_id": "ten-uuid-001",
  "status": "provisioning", "entitlement_id": "ent-uuid-001" }
```
`202 Accepted` · `403` no `resource.create` in tenant · `409` capability set doesn't match what the offering's plugin version declared (J27) · `422` project not found in tenant

### Internal steps
| Step | Domain | Action | DB Write |
|---|---|---|---|
| 1 | Marketplace | Validate offering is `published` | READ `marketplace.offerings` |
| 2 | Marketplace | Validate accepted capabilities match declared set exactly | READ `marketplace.plugin_capabilities` |
| 3 | Marketplace | INSERT installation | `status='provisioning'` |
| 4 | Marketplace | INSERT entitlement | `status='active'`, linked to installation |
| 5 | Marketplace | Emit outbox event | `INSERT outbox_events (type='provision_service')` → consumed by J34 |
| 6 | Audit | Log | `installation.created` |

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.installations.status` | — | `'provisioning'` | `installation.created` |
| `marketplace.entitlements.status` | — | `'active'` | `entitlement.granted` |

---

## Journey 33 — My Entitlements (Read)

**Actor:** Tenant-admin
**Trigger:** Viewing what the tenant currently has access to
**Outcome:** Read-only

### API
`GET /tenants/{tenant_id}/entitlements`
```json
{ "entitlements": [
    { "entitlement_id": "ent-uuid-001", "offering": "Fraud Scoring Suite — Pro",
      "status": "active", "granted_at": "2024-06-15T12:00:00Z",
      "usage": { "transactions_this_period": 41230, "included": 100000 } }
  ] }
```
`200 OK`

**Tables read only:** `marketplace.entitlements`, joined to `marketplace.offerings`, `marketplace.products`. Usage numbers are read from a metering store (out of scope of this doc — treat as an external read).

---

## Journey 34 — Provision Service (Async Worker)

**Actor:** System (background worker consuming the outbox event from J32)
**Trigger:** `provision_service` outbox event
**Outcome:** `marketplace.service_instances` row created · `installations.status` → `active` (or `failed` with retry)

### Internal steps (no external API — worker-triggered)
| Step | Domain | Action | DB Write |
|---|---|---|---|
| 1 | Marketplace | Read pending outbox event | READ `outbox_events WHERE type='provision_service' AND status='pending'` |
| 2 | Marketplace | Call vendor's provisioning webhook / infra API | external call |
| 3 | Marketplace | INSERT service instance | `status='active'`, `installation_id` |
| 4 | Marketplace | UPDATE installation | `status='active'` |
| 5 | Audit | Log | `service_instance.provisioned` |

On failure: `installations.status → 'failed'`, outbox event retried with exponential backoff (same resilience pattern as the Keycloak compensating transaction in J1 and the session-revocation retry in J6).

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.service_instances.status` | — | `'active'` | `service_instance.provisioned` |
| `marketplace.installations.status` | `'provisioning'` | `'active'` / `'failed'` | `installation.activated` / `installation.failed` |

---

## Journey 35 — Review Plugins Queue (Read + Claim)

**Actor:** Platform governance admin
**Trigger:** Opening the governance queue of plugin versions awaiting review
**Outcome:** List is read-only; "claim" prevents two reviewers from deciding the same version simultaneously

### API
`GET /admin/plugin-reviews?status=pending_review`
```json
{ "results": [
    { "version_id": "pv-uuid-001", "plugin": "acme-fraud-scoring", "version": "1.0.0",
      "submitted_at": "2024-06-15T09:00:00Z", "claimed_by": null }
  ] }
```

`POST /admin/plugin-reviews/{version_id}/claim`
```json
{ "version_id": "pv-uuid-001", "claimed_by": "user-uuid-ops-1", "claimed_at": "2024-06-16T07:55:00Z" }
```
`200 OK` · `409` already claimed by another reviewer

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.plugin_versions.claimed_by` | `NULL` | reviewer user_id | `plugin_version.claimed` |

---

## Journey 36 — Approve / Reject Plugin Version (Final Decision)

**Actor:** Platform governance admin (must hold the claim from J35, or claim is optional depending on policy)
**Trigger:** Final governance decision after review (J26)
**Outcome:** `marketplace.plugin_versions.status` → `approved` or `rejected` · on approval, dependent offerings (J30) become publishable

### API
`POST /admin/plugin-reviews/{version_id}/decision`
```json
// Input
{ "decision": "approved", "notes": "Capabilities scoped correctly, SBOM scan clean." }
```
```json
// Output
{ "version_id": "pv-uuid-001", "status": "approved", "decided_by": "user-uuid-ops-1",
  "decided_at": "2024-06-16T08:10:00Z" }
```
`200 OK` · `403` no `governance.review` · `409` not `pending_review` or `changes_requested` · `422` decision must be `approved`/`rejected`

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.plugin_versions.status` | `'pending_review'` | `'approved'` / `'rejected'` | `plugin_version.approved` / `plugin_version.rejected` |
| `marketplace.plugins.status` | `'draft'` | `'active'` (on first version approval) | `plugin.activated` |
| `identity.audit_log` | — | new row | `plugin_version.approved` / `.rejected` |

> Same "never silently overwrite, always keep a decision trail" rule as J11 — a rejected version is kept, not deleted, so a vendor can see exactly why and submit a corrected version (back to J25).

---

## Journey 37 — Vendor Directory & Suspension

**Actor:** Platform governance admin
**Trigger:** Reviewing all vendors on the platform; suspending a vendor for policy violations
**Outcome:** `vendor.profiles.status` → `suspended` · all of that vendor's **published** offerings are unpublished automatically

### API
`GET /admin/vendors?status=verified`
```json
{ "results": [
    { "vendor_id": "vendor-uuid-001", "legal_name": "Acme Corp Pvt Ltd", "status": "verified",
      "product_count": 3, "active_installs": 42 }
  ] }
```

`POST /admin/vendors/{vendor_id}/suspend`
```json
// Input
{ "reason": "Repeated SBOM policy violations across two plugin versions." }
```
```json
// Output
{ "vendor_id": "vendor-uuid-001", "status": "suspended", "offerings_unpublished": 5 }
```
`200 OK` · `403` no `platform.admin` · `409` already suspended

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `vendor.profiles.status` | `'verified'` | `'suspended'` | `vendor.suspended` |
| `marketplace.offerings.status` (bulk) | `'published'` | `'unpublished'` | `offering.unpublished` |
| `identity.audit_log` | — | new row | `vendor.suspended` |

> Existing **installations/entitlements are NOT revoked automatically** on vendor suspension — that is a deliberate, separate, higher-severity action (out of scope here) to avoid silently breaking live tenant integrations over a governance action. This mirrors the JWT-vs-session distinction in J5: suspension stops *new* installs immediately; it does not retroactively tear down running state.

---

## Cross-Journey State Summary (J12–J37)

| Table | J12 | J13 | J14 | J15 | J16 | J17 | J18 | J19 | J20 | J21 | J22 | J23 | J24 | J25 | J26 | J27 | J28 | J29 | J30 | J31 | J32 | J33 | J34 | J35 | J36 | J37 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `tenant.tenants` | INSERT | READ | — | UPDATE | READ | READ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `tenant.projects` | INSERT | INSERT | — | — | READ | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | READ | — | — | — | — | — |
| `tenant.organizations` | READ | — | — | — | — | READ | READ | READ | READ | UPDATE | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `tenant.org_memberships` | — | — | — | — | — | READ | — | INSERT/UPD | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `tenant.tenant_memberships` | — | — | INSERT/UPD | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `tenant.onboarding_checklists` | — | — | — | — | UPDATE | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `identity.identity_realms` | — | — | — | — | — | — | READ/UPD | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `vendor.profiles` | — | — | — | — | — | — | — | — | READ | INSERT | UPDATE | READ | — | — | — | — | — | — | — | READ | — | — | — | — | — | UPDATE |
| `vendor.verifications` | — | — | — | — | — | — | — | — | — | INSERT | UPDATE | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `marketplace.plugins` | — | — | — | — | — | — | — | — | — | — | — | READ | INSERT | READ | READ | READ | READ | READ | — | READ | READ | — | — | — | UPDATE | — |
| `marketplace.plugin_versions` | — | — | — | — | — | — | — | — | — | — | — | — | — | INSERT | UPDATE | UPDATE | READ | — | READ | — | READ | — | — | READ/UPD | UPDATE | — |
| `marketplace.plugin_capabilities` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | READ | INSERT | — | — | — | — | READ | — | — | — | — | — |
| `marketplace.products` | — | — | — | — | — | — | — | — | — | — | — | READ | — | — | — | — | — | INSERT | READ | READ | — | — | — | — | — | READ |
| `marketplace.offerings` | — | — | — | — | — | — | — | — | — | — | — | READ | — | — | — | — | — | — | INSERT/UPD | READ | READ | READ | — | — | — | UPDATE |
| `marketplace.installations` | — | — | — | — | — | — | — | — | — | — | — | READ | — | — | — | — | — | — | — | — | INSERT | — | UPDATE | — | — | — |
| `marketplace.entitlements` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | INSERT | READ | — | — | — | — |
| `marketplace.service_instances` | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | INSERT | — | — | — |
| `authz.roles` | INSERT×3 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `authz.user_roles` | INSERT | — | INSERT/UPD | — | — | — | — | UPD(cascade) | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |
| `identity.audit_log` | INSERT | INSERT | INSERT | INSERT | — | — | — | INSERT | — | INSERT | INSERT | — | INSERT | INSERT | INSERT | INSERT | — | INSERT | INSERT | — | INSERT | — | INSERT | — | INSERT | INSERT |

`INSERT` = new row created · `UPDATE` = existing row modified · `READ` = queried only · `—` = table not touched in this journey.

---

## New tables introduced in this document (not present in Journey 1)

| Schema | Table | Purpose |
|---|---|---|
| `tenant` | `tenant_memberships` | User↔tenant membership, distinct from org-level `org_memberships` |
| `tenant` | `onboarding_checklists` | Per-tenant onboarding progress tracker |
| `vendor` | `profiles` | Vendor legal/business identity, one row per organization-turned-vendor |
| `vendor` | `verifications` | KYC/verification request + decision history for a vendor profile |
| `marketplace` | `plugins` | Technical plugin shell (owned by a vendor) |
| `marketplace` | `plugin_versions` | Versioned builds of a plugin, each independently reviewed |
| `marketplace` | `plugin_capabilities` | Declared scopes/permissions requested by a plugin version |
| `marketplace` | `products` | Commercial product wrapping one or more plugins |
| `marketplace` | `offerings` | Pricing plan under a product |
| `marketplace` | `installations` | A tenant's install of a specific offering |
| `marketplace` | `entitlements` | What a tenant is currently entitled to use, derived from installations |
| `marketplace` | `service_instances` | The provisioned runtime instance backing an active installation |

All of the above reuse `identity.audit_log` for audit trail and `authz.roles` / `authz.user_roles` for permission checks — no new authorization primitives were introduced, consistent with Journey 1's model of roles being resolved fresh from the DB on every request (J10/J11).

---

## Screens not yet mapped to a distinct journey (view-only, safe to build as thin read endpoints)

A few screens are pure dashboards with no independent write behavior of their own — they're intentionally folded into the journeys above rather than given their own number, since each is just a `GET` composing reads from tables already covered:

- **t_dash** (Tenant Dashboard) → reads `tenant.tenants`, `tenant.projects`, `marketplace.entitlements`
- **o_overview** → Journey 17
- **v_portal** → Journey 23
- **p_versions** → Journey 28
- **m_entitle** → Journey 33

End of Tenant, Vendor & Plugin User Journey Reference — TenantPlatform v2 (Phase 2)
