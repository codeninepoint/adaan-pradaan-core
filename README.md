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

## Phase 1 journeys

J01–J06 identity (register → verify → login → refresh → revoke → password reset) plus AuthZ-gated `POST /api/v1/tenants/{tenant_id}/resources`.


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
