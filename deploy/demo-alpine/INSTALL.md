# Demo install — Raspberry Pi

Your board is likely **Raspberry Pi OS (Debian)**, not Alpine. Use `apt` and the **`gnu`** release artifacts.

| OS | Package manager | Init | Artifact libc |
|----|-----------------|------|----------------|
| Raspberry Pi OS / Debian | `apt` | systemd | `*-gnu.tar.gz` |
| Alpine Linux | `apk` | OpenRC | `*-musl.tar.gz` |

## Raspberry Pi OS (recommended)

```sh
sudo apt-get update && sudo apt-get install -y curl
curl -fsSL "https://github.com/codeninepoint/adaan-pradaan-core/releases/download/demo-0.1.2/install-demo.sh" -o install-demo.sh
chmod +x install-demo.sh
sudo ./install-demo.sh --repo codeninepoint/adaan-pradaan-core --version demo-0.1.2
```

The installer:
1. Installs nginx, postgresql, nodejs via `apt`
2. Downloads `*-aarch64-gnu.tar.gz` + ops bundle
3. Unpacks to `/opt/adaan/{core,ui}`
4. Enables systemd units `adaan-api`, `adaan-ui`, `nginx`

### Smoke test

```sh
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1/api/docs
```

Edit `/etc/adaan/core.env` (JWT secret, CORS with your Pi IP), then:

```sh
sudo systemctl restart adaan-api
```

## Manual Debian install

```sh
sudo apt-get install -y nginx postgresql postgresql-contrib nodejs curl tar gzip

sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE USER tenant WITH PASSWORD 'tenant';" || true
sudo -u postgres psql -c "CREATE DATABASE tenant_platform OWNER tenant;" || true

# Download gnu tarballs from the Release, then:
sudo mkdir -p /opt/adaan /etc/adaan
sudo tar -xzf adaan-pradaan-core-linux-aarch64-gnu.tar.gz -C /opt/adaan
sudo tar -xzf adan-pradan-ui-standalone-linux-aarch64-gnu.tar.gz -C /opt/adaan
sudo tar -xzf adaan-demo-pi-ops.tar.gz -C /tmp

sudo cp /tmp/adaan-demo-pi/config/demo.env.example /etc/adaan/core.env
sudo cp /tmp/adaan-demo-pi/nginx/adaan.conf /etc/nginx/sites-available/adaan
sudo ln -sfn /etc/nginx/sites-available/adaan /etc/nginx/sites-enabled/adaan
sudo rm -f /etc/nginx/sites-enabled/default

sudo cp /tmp/adaan-demo-pi/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adaan-api adaan-ui nginx
```

## Alpine (optional)

Use musl Release artifacts (if published) and OpenRC scripts under `openrc/`. Prefer the auto-detecting `install-demo.sh` on Alpine — it selects `*-musl.tar.gz`.

## Notes

- Fake Keycloak: `TENANT_KEYCLOAK_MODE=fake` (do not set `TENANT_APP_ENV=production`)
- Workflows: `TENANT_WORKFLOW_MODE=inline`
- UI is built with `NEXT_PUBLIC_API_URL=/api`
