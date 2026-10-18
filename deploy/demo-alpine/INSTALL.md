# Demo install — Raspberry Pi (Alpine Linux)

Self-contained demo: **Postgres + Core API + Next.js** on one Pi. Keycloak is replaced by in-process `TENANT_KEYCLOAK_MODE=fake`. Temporal is not used (`TENANT_WORKFLOW_MODE=inline`).

## Prerequisites

- Raspberry Pi with **Alpine Linux** (`aarch64`) and internet
- Prefer **4 GB+ RAM**
- Root or `doas`/`sudo` for packages and OpenRC

## Artifacts (GitHub Release)

Published on tags `demo-*` (example `demo-0.1.0`):

| Asset | Install path |
|-------|----------------|
| `adaan-pradaan-core-linux-aarch64-musl.tar.gz` | `/opt/adaan/core` |
| `adan-pradan-ui-standalone-linux-aarch64.tar.gz` | `/opt/adaan/ui` |
| `adaan-demo-alpine-openrc.tar.gz` | nginx, OpenRC, env templates |
| `SHA256SUMS` | verify downloads |

Replace `<org>/<repo>` with `codeninepoint/adaan-pradaan-core` (or your fork) and the tag (e.g. `demo-0.1.0`).

### One-shot installer

```sh
apk add curl tar gzip
curl -fsSL "https://github.com/<org>/<repo>/releases/download/demo-0.1.0/install-demo.sh" -o install-demo.sh
chmod +x install-demo.sh
./install-demo.sh --repo <org>/<repo> --version demo-0.1.0
```

### Manual install

```sh
apk add nginx postgresql postgresql-contrib nodejs curl tar gzip

# Postgres
rc-service postgresql setup   # first boot only, if needed
rc-update add postgresql default
rc-service postgresql start
su - postgres -c "psql -c \"CREATE USER tenant WITH PASSWORD 'tenant';\"" || true
su - postgres -c "psql -c \"CREATE DATABASE tenant_platform OWNER tenant;\"" || true

# Unpack
mkdir -p /opt/adaan /etc/adaan
cd /tmp
curl -fsSLO "https://github.com/<org>/<repo>/releases/download/demo-0.1.0/adaan-pradaan-core-linux-aarch64-musl.tar.gz"
curl -fsSLO "https://github.com/<org>/<repo>/releases/download/demo-0.1.0/adan-pradan-ui-standalone-linux-aarch64.tar.gz"
curl -fsSLO "https://github.com/<org>/<repo>/releases/download/demo-0.1.0/adaan-demo-alpine-openrc.tar.gz"
curl -fsSLO "https://github.com/<org>/<repo>/releases/download/demo-0.1.0/SHA256SUMS"
sha256sum -c SHA256SUMS

tar -xzf adaan-pradaan-core-linux-aarch64-musl.tar.gz -C /opt/adaan
tar -xzf adan-pradan-ui-standalone-linux-aarch64.tar.gz -C /opt/adaan
tar -xzf adaan-demo-alpine-openrc.tar.gz -C /tmp
# Expected dirs: /opt/adaan/core , /opt/adaan/ui

cp /tmp/adaan-demo-alpine/env/demo.env.example /etc/adaan/core.env
# Edit TENANT_JWT_SECRET and TENANT_CORS_ORIGINS (Pi IP / hostname)

cp /tmp/adaan-demo-alpine/nginx/adaan.conf /etc/nginx/http.d/adaan.conf
# Remove or disable conflicting default site if it conflicts on :80

cp /tmp/adaan-demo-alpine/openrc/adaan-api /etc/init.d/adaan-api
cp /tmp/adaan-demo-alpine/openrc/adaan-ui /etc/init.d/adaan-ui
chmod +x /etc/init.d/adaan-api /etc/init.d/adaan-ui /opt/adaan/core/bin/*

rc-update add nginx default
rc-update add adaan-api default
rc-update add adaan-ui default

rc-service adaan-api start
rc-service adaan-ui start
rc-service nginx start
```

## Smoke test

```sh
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/          # UI via nginx
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/api/docs   # API docs via /api strip
```

Open `http://<pi-ip>/` in a browser. The UI calls `/api/...` (same origin).

## Layout

```text
/opt/adaan/core/     Core tarball (.venv, bin/, src/, migrations/)
/opt/adaan/ui/       Next standalone (server.js, .next/static, …)
/etc/adaan/core.env  Runtime env for API
/etc/nginx/http.d/adaan.conf
/etc/init.d/adaan-api
/etc/init.d/adaan-ui
```

## Notes

- UI Release is built with `NEXT_PUBLIC_API_URL=/api` so any Pi hostname works behind nginx.
- Do **not** set `TENANT_APP_ENV=production` for this demo — fake Keycloak is rejected in production.
- Postgres should listen on `127.0.0.1` only.
