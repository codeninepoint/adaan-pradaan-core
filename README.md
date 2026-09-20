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
