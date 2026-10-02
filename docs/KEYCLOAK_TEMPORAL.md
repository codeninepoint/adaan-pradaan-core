# Keycloak and Temporal in this project

This describes the running stack in `adaan-pradaan-core`: which database holds which data, and which code paths actually call Keycloak or Temporal.

## Where the data lives

There are three stores. They are not the same database.

| Store | What it is in Compose | What it holds |
|-------|----------------------|---------------|
| App Postgres | service `postgres`, database `tenant_platform`, host port **5434** | App tables in schemas `identity`, `tenant`, `authz`, `resource`, `vendor`, `platform`. Also Keycloak’s own tables, in schema **`keycloak`** in this same database. |
| Temporal Postgres | service `temporal-db`, database `temporal` | Temporal’s own schema: workflow executions and history. The API never queries this database. |

Keycloak connects with `KC_DB_URL=jdbc:postgresql://postgres:5432/tenant_platform?currentSchema=keycloak` and `KC_DB_SCHEMA=keycloak`. The empty schema is created by `docker/postgres/init-keycloak-schema.sql` (and, on an already-initialized volume, by running that SQL once). Keycloak’s Liquibase then creates tables such as `keycloak.realm` and `keycloak.user_entity` on first start. The app never writes those tables; it only stores references in `identity` and `tenant`.

### What the app Postgres stores about Keycloak

| Table | Columns that point at Keycloak |
|-------|--------------------------------|
| `identity.credentials` | `keycloak_subject` (Keycloak user id), `password_hash` (local bcrypt so a correct password can recreate the Keycloak user if that process lost it) |
| `identity.identity_realms` | `realm_name`, `realm_type` (`platform` or `organization`), `keycloak_realm_id`, `organization_id` |
| `tenant.organizations` | `keycloak_realm_ref` (the realm slug, permanent) |
| `tenant.organization_registration_requests` | `keycloak_realm_ref`, `status` (`processing` / `completed` / `failed`) |

Authorization is also in this Postgres database (`authz.permissions`, `authz.roles`, `authz.role_permissions`, `authz.principal_roles`). Keycloak is not the authorization store. The API issues its own JWT after Keycloak accepts the password. Roles are not copied into that JWT.

## Keycloak

Compose runs `nehathakur123/keycloak:26.0` with `start-dev`. Admin console: http://127.0.0.1:8080 (`admin` / `admin`). The API reaches it at `http://keycloak:8080`.

| Env (set on the API container) | Value in Compose | Meaning |
|--------------------------------|------------------|---------|
| `TENANT_KEYCLOAK_MODE` | `real` | `RealKeycloakClient` (Admin REST + password grant). Default outside Compose is `fake` (in-memory, used by pytest). |
| `TENANT_KEYCLOAK_BASE_URL` | `http://keycloak:8080` | Keycloak base URL |
| `TENANT_KEYCLOAK_CLIENT_ID` | `tenant-platform` | Public client with direct access grants, created in each realm on first use |

`RealKeycloakClient` (`src/identity/infrastructure/keycloak_admin.py`) logs into the `master` realm with `admin-cli`, then:

- creates a realm and the `tenant-platform` client
- creates a user (`username` = email, password not temporary)
- checks a password with the token endpoint and reads `sub` from that token
- sets or recreates a password when the Keycloak user id no longer exists

If Keycloak is down, those calls raise `KeycloakUnavailable` and the API returns **503**.

### Calls the product actually makes

| User action | API | Keycloak call | App Postgres write |
|-------------|-----|---------------|--------------------|
| Sign up | `POST /auth/register` | `create_user` in realm `platform` (realm and client are created on first 404) | `identity.users`, `identity.principals`, `identity.credentials` (`keycloak_subject` + `password_hash`), individual org |
| Sign up rolls back | same request, on failure | `delete_user` | transaction rolled back |
| Sign in | `POST /auth/token` | password grant `authenticate` | session row; if the Keycloak user is missing but `password_hash` matches, `set_password` recreates the user and updates `keycloak_subject` |
| Reset password | `POST /auth/password/reset` | `set_password` (creates the user if the old subject is gone) | new `password_hash`, updated `keycloak_subject`, sessions revoked |
| Upgrade to an organization | `POST /api/v1/organizations/register` | `create_realm` named the slug, plus client `tenant-platform` | org `org_type=organization`, `keycloak_realm_ref=slug`, realm row, default tenant `{slug}-default` |

Email verification (`POST /auth/verify-email`) does not call Keycloak. It only flips the local user and principal to `active`. Login is refused until that happens.

Vendor approval, member invites, resources, and role grants do not call Keycloak.

## Temporal

Compose runs `nehathakur123/temporal:1.25.2` on port **7233**, backed by `temporal-db`. One worker container runs `python -m workflows.worker` on task queue `org-upgrade`.

| Env | Value in Compose | Meaning |
|-----|------------------|---------|
| `TENANT_WORKFLOW_MODE` | `temporal` | Org upgrade returns `processing` and finishes in the worker. Default outside Compose is `inline` (the HTTP request does the work; pytest uses this). |
| `TENANT_TEMPORAL_ADDRESS` | `temporal:7233` | Frontend address |
| `TENANT_TEMPORAL_TASK_QUEUE` | `org-upgrade` | Queue the worker polls |

The only workflow is **J07 organization upgrade**.

1. `POST /api/v1/organizations/register` inserts `organization_registration_requests` with `status=processing` and commits.
2. `workflows.starter.start_org_upgrade` starts workflow id `org-upgrade-{request_id}`, name `OrgUpgradeWorkflow`.
3. The worker runs activity `run_org_upgrade`, which calls `OrgUpgradeService.run_for_request`.
4. That activity creates the Keycloak realm and the org, tenant, membership, and `tenant-admin` binding in app Postgres, then sets the request to `completed` or `failed`.
5. The UI (and any client) polls `GET /api/v1/organizations/register/{request_id}` until the status is terminal.

`KeycloakUnavailable` is retried (up to 5 attempts, starting at 2 seconds). Any other error marks the request `failed` and does not retry. If Temporal cannot be reached when the request is accepted, the API marks the request `failed` immediately.

Login, registration, password reset, vendor KYC, and resource APIs do not start a Temporal workflow. With `TENANT_WORKFLOW_MODE=inline`, the same org-upgrade pipeline runs inside the API process and the POST returns `completed` without a worker.

## What to check when something fails

- Sign-in returns invalid credentials, and the user exists in `identity.users` but not in the Keycloak `platform` realm: the Keycloak volume was empty or the account was created under fake mode (subject looks like `kc-…`) before a password hash existed. Use forgot-password once so `set_password` creates the real user.
- Org register stays `processing`: the worker is not connected. `docker compose logs worker` should show it polling `org-upgrade`. Temporal must be healthy before the worker starts (`restart: on-failure` covers a slow Temporal boot).
- Org register returns 503: Keycloak is not accepting connections yet.
