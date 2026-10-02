# adaan-pradaan-core

Python FastAPI control-plane backend for multi-tenant marketplace identity, authorization, and resources.

## Stack

- FastAPI + SQLAlchemy (async) + Alembic + PostgreSQL
- Lean JWT auth (no roles in token) + refresh rotation
- Live DB AuthZ (`AuthorizationService`)

## Layout

```
src/identity|authz|tenant|resources|shared|api
migrations/
tests/
openapi/
docs/
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d postgres
alembic upgrade head
uvicorn api.main:app --reload --app-dir src
```

API docs: http://127.0.0.1:8000/docs

### Keycloak + Temporal (docker compose)

`docker compose up --build` starts Postgres, **Keycloak** (`http://127.0.0.1:8080`, admin/admin), **Temporal** (`7233`), the API, and a worker. The API container sets `TENANT_KEYCLOAK_MODE=real` and `TENANT_WORKFLOW_MODE=temporal`. Pytest keeps `fake` + `inline`.

| Env | Meaning |
|-----|---------|
| `TENANT_KEYCLOAK_MODE=real` | Admin API + password grant (`RealKeycloakClient`). `fake` stays the default for pytest. |
| `TENANT_WORKFLOW_MODE=temporal` | J07 org upgrade returns `processing` and `OrgUpgradeWorkflow` finishes realm provisioning. `inline` (default outside compose) runs the pipeline in the request so tests stay synchronous. |

Vendor KYC stays a request plus a human decision (no long-running workflow). Login, register, and password reset use Keycloak directly, not Temporal.

The API container already running from an older image is still **fake** Keycloak until you rebuild. `docker compose up --build` failed here because Docker Hub rejected the pull (`authentication required`). Run `docker login`, then:

```bash
docker compose up --build -d
docker compose ps
```

Wait until Keycloak answers (`curl -sf http://127.0.0.1:8080/realms/master`) and the API docs load (`http://127.0.0.1:8000/docs`). Then:

```bash
# 1. Register — creates the platform realm + user in real Keycloak. Copy dev_otp.
curl -s -X POST http://127.0.0.1:8000/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"SecurePass123!","display_name":"Alice","agreed_to_terms":true}'

# 2. Verify, then login. Save access_token.
curl -s -X POST http://127.0.0.1:8000/auth/verify-email \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","otp_code":"PASTE_OTP"}'
curl -s -X POST http://127.0.0.1:8000/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"SecurePass123!"}'

# 3. Org upgrade — Temporal. First response should be status "processing", not "completed".
curl -s -X POST http://127.0.0.1:8000/api/v1/organizations/register \
  -H "Authorization: Bearer PASTE_TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Acme Corp","slug":"acme-corp","contact_name":"Alice","contact_email":"alice@example.com","country":"IN"}'

# 4. Poll until completed (worker + Keycloak realm acme-corp).
curl -s http://127.0.0.1:8000/api/v1/organizations/register/PASTE_REQUEST_ID \
  -H "Authorization: Bearer PASTE_TOKEN"
```

Confirm the processes, not only the HTTP status:

- Keycloak admin `http://127.0.0.1:8080` (admin/admin): realm `platform` has `alice@example.com`; after the poll, realm `acme-corp` exists with client `tenant-platform`.
- `docker compose logs worker` shows `OrgUpgradeWorkflow` / `run_org_upgrade` finishing without error.
- If the poll stays `processing`, the worker is not connected to Temporal (`temporal:7233`). If register returns 503, Keycloak is not up yet.

### With the UI ([adan-pradan-ui](https://github.com/codeninepoint/adan-pradan-ui))

1. Start this API (`docker compose up --build` or uvicorn above) on `:8000`.
2. In the UI repo: set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` and run `pnpm dev` / `npm run dev` on `:3000`.

CORS origins are controlled by `TENANT_CORS_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`).
In `dev`/`test`, `POST /auth/register` returns `dev_otp` and `POST /auth/password/reset-request` returns `dev_reset_token`.
**Staging / production:** set `TENANT_APP_ENV=production` (and a strong `TENANT_JWT_SECRET`). The API will not emit `dev_otp` / `dev_reset_token`; the UI only shows those fields when the API returns them.
`GET /auth/me` returns the signed-in user, orgs, and tenants for the UI session shell (`/app`).

**Full walkthrough** (every API in order, request/response/DB, UI wiring, CORS explained): [docs/API_UI_CORS_GUIDE.md](docs/API_UI_CORS_GUIDE.md).

## Phase 1 journeys

J01–J06 identity (register → verify → login → refresh → revoke → password reset), AuthZ-gated resources, J07–J11 org/roles/SA, and J14/J19/J20–J22 invites/vendor — see the guide above.


## Docker

```bash
# build API image
docker build -t adaan-pradaan-core:latest .

# run API + Postgres
docker compose up --build
```

API: http://127.0.0.1:8000/docs


## CI/CD (GitHub Actions → Docker Hub)

On every push to `main`, GitHub Actions builds and pushes:

- `<DOCKERHUB_USERNAME>/adaan-pradaan-core:latest`
- `<DOCKERHUB_USERNAME>/adaan-pradaan-core:sha-<commit>`

Pull requests only **build** (no push) to validate the Dockerfile.

### One-time setup

1. Create a Docker Hub Access Token: https://hub.docker.com/settings/security
2. In GitHub repo **Settings → Secrets and variables → Actions**, add:
   - `DOCKERHUB_USERNAME` — your Docker Hub username (or org)
   - `DOCKERHUB_TOKEN` — the access token (not your password)
3. (Optional) Create public repos on Docker Hub named `adaan-pradaan-core` (auto-created on first push for many accounts).

Pull the published image:

```bash
docker pull <DOCKERHUB_USERNAME>/adaan-pradaan-core:latest
```
