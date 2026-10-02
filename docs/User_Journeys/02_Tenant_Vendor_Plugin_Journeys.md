# Tenant, Vendor & Plugin — Complete User Journey Reference
### J12–J52 · Every API · Every Table · Every State Change
**Multi-Tenant Cloud Platform — Phase 2** (continues numbering from Journey 1: Identity & Authorization, J1–J11)

> Companion document to `01_Identity_Auth_Journeys` (J1–J11). This document covers everything that happens **after** a user has registered, verified, logged in, and optionally upgraded to an Organization (J7). J12–J37 map onto the 28 screens in [Adanpradan_Identity auth tenant vendor_Flow.html](../UI%20Screems_Html/Adanpradan_Identity%20auth%20tenant%20vendor_Flow.html). J38–J52 cover the later vendor portal and buyer storefront in [vendor_plugin_portal1.html](../UI%20Screems_Html/vendor_plugin_portal1.html) and [marketplace_portal.html](../UI%20Screems_Html/marketplace_portal.html).

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
| J38 | Vendor install list (read) | Vendor admin | `marketplace.installations` (read) | vendor portal `installs` |
| J39 | Product list, edit, archive | Vendor admin | `marketplace.products`, `identity.audit_log` | vendor portal `products` |
| J40 | Fulfilment-typed product wizard | Vendor admin | `marketplace.products`, `marketplace.product_content`, `marketplace.offerings` | vendor portal `new-product` |
| J41 | Marketplace home (read) | Buyer | `marketplace.offerings`, `marketplace.products` (read) | buyer `home` |
| J42 | Product detail (read) | Buyer | `marketplace.products`, `marketplace.product_content`, `marketplace.offerings` (read) | buyer `detail` |
| J43 | Wishlist | Tenant member | `marketplace.wishlists` | buyer `wishlist` |
| J44 | Cart | Tenant member | `marketplace.carts`, `marketplace.cart_lines` | buyer `cart` |
| J45 | Vendor revenue and payouts (read) | Vendor admin | `marketplace.payouts` (read) | vendor portal `revenue` |
| J46 | Vendor business settings | Vendor admin | `vendor.settings`, `identity.audit_log` | vendor portal `settings` |
| J47 | Vendor support request | Vendor admin | `vendor.support_requests`, `identity.audit_log` | vendor portal `support` |
| J48 | Checkout / place order | Tenant-admin | `marketplace.orders`, `marketplace.order_lines`, `marketplace.installations` | buyer `checkout` |
| J49 | Orders and tracking (read) | Tenant member | `marketplace.orders` (read) | buyer `orders`, `order-detail` |
| J50 | Returns | Tenant member | `marketplace.returns`, `identity.audit_log` | buyer `returns` |
| J51 | Buyer subscriptions (read) | Tenant-admin | `marketplace.orders`, billing subscription (read) | buyer `billing` |
| J52 | Delivery addresses | Tenant member | `tenant.addresses` | buyer `addresses` |

**Column colour coding (kept consistent with Journey 1):** INDIGO = `identity.*` · TEAL = `tenant.*` · CORAL = `vendor.*` · PURPLE = `marketplace.*` · AMBER = PK / state column · RED = `authz.*` writes.

## Screen crosswalk — later portals

J12–J37 stay bound to [Adanpradan_Identity auth tenant vendor_Flow.html](../UI%20Screems_Html/Adanpradan_Identity%20auth%20tenant%20vendor_Flow.html). Governance screens `g_plugins`, `g_approve`, and `g_vendors` (J35–J37) are not in the two HTML files below.

### Vendor portal — `vendor_plugin_portal1.html`

| Page | Journey |
|---|---|
| Dashboard | J23 (counts). Checklist and recent installs are the same read, not a new write. |
| Active Installs | J38 |
| Revenue & Payouts | J45 |
| My Products | J39 |
| Add New Product | J40, which extends J29 and J30 |
| Listing Standards | Static reference for the nine fulfilment types. No API. |
| My Plugin | J24 (identity) and J28 (version history). Adapter URL and health are fields on the plugin read. |
| Submit New Version | J25 and J27 |
| Business Settings | J46 |
| Support | J47 |

### Buyer storefront — `marketplace_portal.html`

| Page | Journey |
|---|---|
| Marketplace Home | J41 |
| Browse All | J31, with the extra filters listed on J31 |
| Product detail | J42. Software and cloud “install” still calls J32. |
| Wishlist | J43 |
| Cart | J44 |
| Checkout | J48 |
| My Installs | J33, plus J34 status |
| Orders & order detail | J49 |
| Returns & Refunds | J50 |
| Subscriptions & Billing | J51 |
| Addresses | J52 |
| Settings | Buyer display preferences only. No new auth journey. |

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

> The vendor portal dashboard in `vendor_plugin_portal1.html` is this read. The install list is J38. Revenue on that page is J45.

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

> The vendor portal “Add New Product” wizard is J40. It calls this create, then stores fulfilment content, then creates the offering in J30.

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

> Publish still requires an approved plugin version (J36). The wizard’s price and billing period are this offering. Fulfilment type lives on the product (J40), not on the offering.

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

> Buyer “Browse All” in `marketplace_portal.html` is this endpoint. Optional query params from that screen: `category`, `vendor_id`, `verified_only`, `price_min`, `price_max`, `sort` (`newest` | `price_asc` | `price_desc`). Marketplace home rails are J41, not this list.

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

## Journey 38 — Vendor Install List (Read)

**Actor:** Vendor admin
**Trigger:** Opening Active Installs on the vendor portal
**Outcome:** Read-only list of tenant installations of this vendor's offerings

### API
`GET /vendors/{vendor_id}/installations`
```json
{ "installations": [
    { "installation_id": "inst-uuid-001", "tenant_name": "MindBloom Studio",
      "product_name": "Gratitude Journal Pro", "fulfilment_type": "SHIP_PHYSICAL",
      "status": "active", "since": "2024-04-01T00:00:00Z" }
  ] }
```
`200 OK` · `403` caller is not this vendor's admin

**Tables read only:** `marketplace.installations` joined to `marketplace.offerings`, `marketplace.products`, `tenant.tenants`. No writes. J23 returns the count; this journey returns the rows.

---

## Journey 39 — Product List, Edit, Archive

**Actor:** Vendor admin
**Trigger:** Opening My Products, editing a listing, or archiving it
**Outcome:** Product row updated in place. Archived products stay queryable. They leave the public catalog.

### API
`GET /vendors/{vendor_id}/products`
```json
{ "products": [
    { "product_id": "prod-uuid-001", "name": "Gratitude Journal Pro",
      "fulfilment_type": "SHIP_PHYSICAL", "status": "published" }
  ] }
```

`PATCH /products/{product_id}`
```json
{ "name": "Gratitude Journal Pro", "description": "Hardcover A5 journal." }
```
```json
{ "product_id": "prod-uuid-001", "status": "published" }
```

`POST /products/{product_id}/archive`
```json
{ "product_id": "prod-uuid-001", "status": "archived", "archived_at": "2024-06-01T00:00:00Z" }
```
`200 OK` · `403` not this vendor's admin · `409` already archived

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.products` (edit) | prior name/description | updated fields | `product.updated` |
| `marketplace.products.status` (archive) | `'published'` or `'draft'` | `'archived'` | `product.archived` |

> Purge warning at 24 months after `archived_at` is a product rule for a later job. This journey does not delete the row. Active installations of an archived product stay active (same rule as J37: existing installs are not torn down).

---

## Journey 40 — Fulfilment-Typed Product Wizard

**Actor:** Vendor admin
**Trigger:** Add New Product wizard (details, fulfilment type, content, price)
**Outcome:** Draft product with one fulfilment type and type-specific content, plus a draft offering (J30)

Allowed `fulfilment_type` values:

| Code | Buyer path after publish |
|---|---|
| `PROVISION_SOFTWARE` | J32 install, then J34 provision |
| `PROVISION_CLOUD` | J32 install, then J34 provision |
| `SHIP_PHYSICAL` | J44 cart, J48 order, shipment |
| `DELIVER_DIGITAL` | J44 cart, J48 order, file delivery |
| `LICENSE_SOFTWARE` | J44 cart, J48 order, license delivery |
| `STREAM_LMS_COURSE` | J44 cart, J48 order, course access |
| `DELIVER_MULTIMEDIA` | J44 cart, J48 order, stream access |
| `DISPATCH_SERVICE` | J44 cart, J48 order, dispatch |
| `BOOK_APPOINTMENT` | J44 cart, J48 order, booking |

### API
Extends J29. Same `POST /vendors/{vendor_id}/products`, with `fulfilment_type` required.
```json
{ "name": "Gratitude Journal Pro", "description": "Hardcover A5 journal.",
  "plugin_id": "plugin-uuid-001", "fulfilment_type": "SHIP_PHYSICAL",
  "content": { "sku": "GJP-A5", "weight_g": 400, "ships_from_pincode": "400001" } }
```
```json
{ "product_id": "prod-uuid-001", "status": "draft", "fulfilment_type": "SHIP_PHYSICAL" }
```
`201 Created` · `422` unknown `fulfilment_type` · `403` vendor not verified · `404` plugin not owned by vendor

Content is stored on `marketplace.product_content` (`product_id`, `payload` JSON). The wizard's price step is J30 (`POST /products/{product_id}/offerings`). Publish remains `POST /offerings/{offering_id}/publish` and still returns `409` until a plugin version is `approved` (J36).

Listing Standards in the vendor portal is the human-readable checklist for `content`. It is not an endpoint.

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.products.status` | — | `'draft'` | `product.created` |
| `marketplace.products.fulfilment_type` | — | one of the nine codes | `product.created` |
| `marketplace.product_content` | — | payload row | `product.created` |

---

## Journey 41 — Marketplace Home (Read)

**Actor:** Any visitor (browse). Signed-in tenant member for the recently-viewed rail.
**Trigger:** Opening Marketplace Home
**Outcome:** Read-only rails. No cart or install.

### API
`GET /marketplace/home`
```json
{ "categories": ["Lifestyle & Wellness", "Digital Products"],
  "rails": {
    "new": [],
    "sponsored": [],
    "trending": []
  } }
```
`200 OK`. Recently viewed is `GET /marketplace/home?tenant_id={tenant_id}` and requires Bearer. Each card is a published product summary (name, vendor, fulfilment type, starting price). Full filterable list remains J31.

**Tables read only:** `marketplace.offerings` where `status='published'`, joined to `marketplace.products` and `vendor.profiles`.

---

## Journey 42 — Product Detail (Read)

**Actor:** Any visitor
**Trigger:** Opening a product card
**Outcome:** Read-only detail used by install (J32) or add-to-cart (J44)

### API
`GET /marketplace/products/{product_id}`
```json
{ "product_id": "prod-uuid-001", "name": "Gratitude Journal Pro",
  "fulfilment_type": "SHIP_PHYSICAL", "vendor": "Happy Minds",
  "content": { "variants": ["A5 Teal"] },
  "offerings": [
    { "offering_id": "off-uuid-001", "plan_name": "Per unit", "price_inr": 499, "status": "published" }
  ] }
```
`200 OK` · `404` not published (draft and archived are hidden from buyers)

**Tables read only:** `marketplace.products`, `marketplace.product_content`, `marketplace.offerings`.

---

## Journey 43 — Wishlist

**Actor:** Tenant member
**Trigger:** Save or remove a product on the buyer storefront
**Outcome:** One wishlist row per tenant + product

### API
`GET /tenants/{tenant_id}/wishlist`
`POST /tenants/{tenant_id}/wishlist`
```json
{ "product_id": "prod-uuid-001" }
```
`DELETE /tenants/{tenant_id}/wishlist/{product_id}`

`201 Created` · `200 OK` on delete · `409` already saved · `404` product not published · `403` not a member of the tenant

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.wishlists` | — | row `(tenant_id, product_id)` | — (no audit; preference only) |
| `marketplace.wishlists` (delete) | row | removed | — |

---

## Journey 44 — Cart

**Actor:** Tenant member
**Trigger:** Add, change quantity, or remove a line before checkout
**Outcome:** One open cart per tenant. Lines reference a published offering.

### API
`GET /tenants/{tenant_id}/cart`
`POST /tenants/{tenant_id}/cart/lines`
```json
{ "offering_id": "off-uuid-001", "quantity": 1 }
```
`PATCH /tenants/{tenant_id}/cart/lines/{line_id}`
```json
{ "quantity": 2 }
```
`DELETE /tenants/{tenant_id}/cart/lines/{line_id}`

`200 OK` · `404` offering not published · `409` line already present (PATCH quantity instead) · `403` not a member

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.carts` | — | `status='open'` | — |
| `marketplace.cart_lines` | — | line with `offering_id`, `quantity` | — |

Software and cloud products (`PROVISION_SOFTWARE`, `PROVISION_CLOUD`) are not cart lines. Those buyers call J32 directly from the product detail page.

---

## Journey 45 — Vendor Revenue and Payouts (Read)

**Actor:** Vendor admin
**Trigger:** Opening Revenue & Payouts
**Outcome:** Read-only ledger. No payment capture in this journey.

### API
`GET /vendors/{vendor_id}/payouts`
```json
{ "currency": "INR",
  "this_period": { "gross": 293612, "platform_fee": 58722, "net": 234890, "status": "paid" },
  "payouts": [
    { "period": "2024-06", "gross": 293612, "platform_fee": 58722, "net": 234890, "status": "paid" }
  ] }
```
`200 OK` · `403` not this vendor's admin

Platform fee is 20% of gross. The remaining split (vendor payout vs builder attribution) is recorded on the payout row and is not calculated in the request. A payment processor is out of scope.

**Tables read only:** `marketplace.payouts`.

---

## Journey 46 — Vendor Business Settings

**Actor:** Vendor admin
**Trigger:** Saving support email, bank details, or notification preferences
**Outcome:** `vendor.settings` updated. Legal name and tax id from J21 are not writable here.

### API
`GET /vendors/{vendor_id}/settings`
`PATCH /vendors/{vendor_id}/settings`
```json
{ "support_email": "support@happyminds.io",
  "bank_account_name": "Happy Minds Pvt Ltd",
  "bank_account_number": "XXXX1234",
  "bank_ifsc": "HDFC0001234",
  "notify_install": true, "notify_payout": true }
```
```json
{ "vendor_id": "vendor-uuid-001", "status": "verified" }
```
`200 OK` · `403` not this vendor's admin · `422` invalid email or IFSC

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `vendor.settings` | prior or empty | updated fields | `vendor.settings_updated` |

`vendor.profiles.legal_name` and tax id stay as written in J21.

---

## Journey 47 — Vendor Support Request

**Actor:** Vendor admin
**Trigger:** Submitting the support form
**Outcome:** A support request row. No ticket workflow beyond create and list.

### API
`POST /vendors/{vendor_id}/support-requests`
```json
{ "subject": "Payout delayed", "message": "June payout still pending." }
```
```json
{ "request_id": "sup-uuid-001", "status": "open" }
```
`201 Created` · `403` not this vendor's admin

`GET /vendors/{vendor_id}/support-requests` lists the vendor's own requests.

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `vendor.support_requests.status` | — | `'open'` | `vendor.support_requested` |

---

## Journey 48 — Checkout

**Actor:** Tenant-admin
**Trigger:** Proceed to checkout from the cart (J44)
**Outcome:** An order. Cart becomes `checked_out`. Provisioned fulfilment types are not in this cart (see J44).

### API
`POST /tenants/{tenant_id}/orders`
```json
{ "address_id": "addr-uuid-001", "payment_method": "upi" }
```
```json
{ "order_id": "ord-uuid-001", "status": "placed", "line_count": 2 }
```
`201 Created` · `409` cart empty · `422` a physical, dispatch, or appointment line has no `address_id` · `403` caller lacks `resource.create` in the tenant

### Internal steps
| Step | Domain | Action | DB Write |
|---|---|---|---|
| 1 | Marketplace | Load open cart and lines | READ `marketplace.carts`, `marketplace.cart_lines` |
| 2 | Marketplace | Require address when any line is `SHIP_PHYSICAL`, `DISPATCH_SERVICE`, or `BOOK_APPOINTMENT` | READ `tenant.addresses` |
| 3 | Marketplace | INSERT order + lines copied from the cart | `orders.status='placed'` |
| 4 | Marketplace | Close the cart | `carts.status='checked_out'` |
| 5 | Audit | Log | `order.placed` |

Payment capture is not performed. `payment_method` is stored on the order for a later billing integration.

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.orders.status` | — | `'placed'` | `order.placed` |
| `marketplace.order_lines` | — | one row per cart line | `order.placed` |
| `marketplace.carts.status` | `'open'` | `'checked_out'` | `order.placed` |

---

## Journey 49 — Orders and Tracking (Read)

**Actor:** Tenant member
**Trigger:** Opening Orders or an order detail page
**Outcome:** Read-only

### API
`GET /tenants/{tenant_id}/orders`
`GET /orders/{order_id}`
```json
{ "order_id": "ord-uuid-001", "status": "placed",
  "lines": [ { "product_name": "Gratitude Journal Pro", "quantity": 1, "fulfilment_type": "SHIP_PHYSICAL" } ],
  "tracking": null }
```
`200 OK` · `403` order's tenant is not one the caller belongs to · `404` unknown order

**Tables read only:** `marketplace.orders`, `marketplace.order_lines`.

---

## Journey 50 — Returns

**Actor:** Tenant member
**Trigger:** Requesting a return on an order line
**Outcome:** `marketplace.returns` row `status='requested'`

### API
`POST /orders/{order_id}/returns`
```json
{ "line_id": "ol-uuid-001", "reason": "Damaged on arrival", "notes": "" }
```
```json
{ "return_id": "ret-uuid-001", "status": "requested" }
```
`201 Created` · `403` not a member of the order's tenant · `409` a return is already open for this line · `422` order is not `placed` or `fulfilled`

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `marketplace.returns.status` | — | `'requested'` | `return.requested` |

Refund execution is out of scope. This journey records the request only.

---

## Journey 51 — Buyer Subscriptions (Read)

**Actor:** Tenant-admin
**Trigger:** Opening Subscriptions & Billing
**Outcome:** Read-only list of recurring offerings the tenant holds. Meter math and invoices stay in the billing domain.

### API
`GET /tenants/{tenant_id}/subscriptions`
```json
{ "subscriptions": [
    { "offering_id": "off-uuid-002", "product_name": "Guided Journal Suite",
      "plan_name": "Monthly", "status": "active", "next_billing_at": "2024-07-01T00:00:00Z" }
  ], "active_count": 1 }
```
`200 OK` · `403` caller lacks `resource.read` in the tenant

Rows are offerings on active installations (J32) or recurring order lines whose billing period is not `one_time`. Cancel is `POST /tenants/{tenant_id}/subscriptions/{offering_id}/cancel` and sets that installation or order line `status='cancel_at_period_end'`. It does not call a payment provider.

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| installation or order line `status` (cancel only) | `'active'` | `'cancel_at_period_end'` | `subscription.cancel_scheduled` |

---

## Journey 52 — Delivery Addresses

**Actor:** Tenant member
**Trigger:** Adding or editing an address used by checkout (J48)
**Outcome:** Address rows scoped to the tenant

### API
`GET /tenants/{tenant_id}/addresses`
`POST /tenants/{tenant_id}/addresses`
```json
{ "label": "Head Office", "contact_name": "MindBloom Studio",
  "line1": "12 Linking Road", "city": "Mumbai", "state": "MH",
  "pincode": "400001", "phone": "+919800000000" }
```
`PATCH /tenants/{tenant_id}/addresses/{address_id}`
`DELETE /tenants/{tenant_id}/addresses/{address_id}`

`201 Created` · `200 OK` · `403` not a member · `409` delete refused when the address is on an order that is not yet `fulfilled`

### State changes
| Table / Column | Before | After | Audit Event |
|---|---|---|---|
| `tenant.addresses` | — | row `status='active'` | — |

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
| `marketplace` | `product_content` | JSON payload for one fulfilment type on a product (J40) |
| `marketplace` | `wishlists` | Tenant saved products (J43) |
| `marketplace` | `carts` | One open cart per tenant (J44) |
| `marketplace` | `cart_lines` | Offering + quantity on an open cart |
| `marketplace` | `orders` | Checkout result (J48) |
| `marketplace` | `order_lines` | Lines copied from the cart at checkout |
| `marketplace` | `returns` | Return request against an order line (J50) |
| `marketplace` | `payouts` | Vendor period ledger, read in J45. Writers are a later billing job |
| `vendor` | `settings` | Support email, bank, notification prefs (J46) |
| `vendor` | `support_requests` | Vendor support form (J47) |
| `tenant` | `addresses` | Delivery addresses for checkout (J52) |

J38–J52 touch those tables as follows. Reads do not write audit rows. J39 updates or archives `marketplace.products`. J40 inserts `marketplace.products` and `marketplace.product_content`. J43–J44 write wishlist and cart tables without audit. J46 updates `vendor.settings`. J47 inserts `vendor.support_requests`. J48 inserts orders and closes the cart. J50 inserts `marketplace.returns`. J51 cancel sets `cancel_at_period_end`. J52 inserts `tenant.addresses`.

All of the above reuse `identity.audit_log` for audit trail and `authz.roles` / `authz.user_roles` for permission checks — no new authorization primitives were introduced, consistent with Journey 1's model of roles being resolved fresh from the DB on every request (J10/J11).

---

## Screens not yet mapped to a distinct journey (view-only, safe to build as thin read endpoints)

A few screens are pure dashboards with no independent write behavior of their own — they're intentionally folded into the journeys above rather than given their own number, since each is just a `GET` composing reads from tables already covered:

- **t_dash** (Tenant Dashboard) → reads `tenant.tenants`, `tenant.projects`, `marketplace.entitlements`
- **o_overview** → Journey 17
- **v_portal** → Journey 23
- **p_versions** → Journey 28
- **m_entitle** → Journey 33
- **Listing Standards** (vendor portal) → static checklist for J40 fulfilment types. No endpoint.
- **Buyer settings** (marketplace portal) → display preferences only. No journey.

End of Tenant, Vendor & Plugin User Journey Reference — TenantPlatform v2 (Phase 2)
