#!/bin/sh
# Download Adaan demo release assets and install on Alpine (aarch64).
# Usage:
#   ./install-demo.sh --repo OWNER/REPO --version demo-0.1.0
#   ./install-demo.sh --base-url https://github.com/OWNER/REPO/releases/download/demo-0.1.0
set -eu

REPO=""
VERSION=""
BASE_URL=""
PREFIX="/opt/adaan"
ENV_DIR="/etc/adaan"

usage() {
	sed -n '2,6p' "$0" | tr -d '#'
	exit 1
}

while [ $# -gt 0 ]; do
	case "$1" in
		--repo) REPO="${2:-}"; shift 2 ;;
		--version) VERSION="${2:-}"; shift 2 ;;
		--base-url) BASE_URL="${2:-}"; shift 2 ;;
		-h|--help) usage ;;
		*) echo "Unknown arg: $1" >&2; usage ;;
	esac
done

if [ -z "${BASE_URL}" ]; then
	if [ -z "${REPO}" ] || [ -z "${VERSION}" ]; then
		echo "Provide --repo OWNER/REPO --version demo-X.Y.Z  or  --base-url URL" >&2
		exit 1
	fi
	BASE_URL="https://github.com/${REPO}/releases/download/${VERSION}"
fi

need_root() {
	if [ "$(id -u)" -ne 0 ]; then
		echo "Re-run as root (or with doas/sudo)." >&2
		exit 1
	fi
}

need_root

echo "==> Installing Alpine packages"
apk add --no-cache nginx postgresql postgresql-contrib nodejs curl tar gzip coreutils

echo "==> Ensuring Postgres is running"
if [ ! -d /var/lib/postgresql/*/data ] 2>/dev/null && ! ls /var/lib/postgresql/*/data >/dev/null 2>&1; then
	if command -v postgresql-setup >/dev/null 2>&1; then
		postgresql-setup --initdb || true
	elif [ -x /etc/init.d/postgresql ]; then
		rc-service postgresql setup 2>/dev/null || true
	fi
fi
rc-update add postgresql default 2>/dev/null || true
rc-service postgresql start || true

echo "==> Ensuring DB role/database"
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='tenant'\"" | grep -q 1 \
	|| su - postgres -c "psql -c \"CREATE USER tenant WITH PASSWORD 'tenant';\""
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='tenant_platform'\"" | grep -q 1 \
	|| su - postgres -c "psql -c \"CREATE DATABASE tenant_platform OWNER tenant;\""

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT
cd "${WORKDIR}"

CORE_TGZ="adaan-pradaan-core-linux-aarch64-musl.tar.gz"
UI_TGZ="adan-pradan-ui-standalone-linux-aarch64.tar.gz"
OPS_TGZ="adaan-demo-alpine-openrc.tar.gz"

echo "==> Downloading from ${BASE_URL}"
curl -fsSLO "${BASE_URL}/${CORE_TGZ}"
curl -fsSLO "${BASE_URL}/${UI_TGZ}"
curl -fsSLO "${BASE_URL}/${OPS_TGZ}"
curl -fsSLO "${BASE_URL}/SHA256SUMS"
sha256sum -c SHA256SUMS

echo "==> Unpacking to ${PREFIX}"
mkdir -p "${PREFIX}" "${ENV_DIR}"
tar -xzf "${CORE_TGZ}" -C "${PREFIX}"
tar -xzf "${UI_TGZ}" -C "${PREFIX}"
tar -xzf "${OPS_TGZ}" -C "${WORKDIR}"

# Normalize names: tarballs contain top-level core/ and ui/
if [ -d "${PREFIX}/adaan-pradaan-core" ] && [ ! -d "${PREFIX}/core" ]; then
	mv "${PREFIX}/adaan-pradaan-core" "${PREFIX}/core"
fi
if [ -d "${PREFIX}/adan-pradan-ui" ] && [ ! -d "${PREFIX}/ui" ]; then
	mv "${PREFIX}/adan-pradan-ui" "${PREFIX}/ui"
fi

OPS_DIR="${WORKDIR}/adaan-demo-alpine"
if [ ! -d "${OPS_DIR}" ]; then
	OPS_DIR="$(find "${WORKDIR}" -maxdepth 2 -type d -name 'demo-alpine' -o -name 'adaan-demo-alpine' | head -n1)"
fi

if [ ! -f "${ENV_DIR}/core.env" ]; then
	cp "${OPS_DIR}/config/demo.env.example" "${ENV_DIR}/core.env"
	echo "Wrote ${ENV_DIR}/core.env — edit TENANT_JWT_SECRET and TENANT_CORS_ORIGINS"
fi

cp "${OPS_DIR}/nginx/adaan.conf" /etc/nginx/http.d/adaan.conf
cp "${OPS_DIR}/openrc/adaan-api" /etc/init.d/adaan-api
cp "${OPS_DIR}/openrc/adaan-ui" /etc/init.d/adaan-ui
chmod +x /etc/init.d/adaan-api /etc/init.d/adaan-ui
chmod +x "${PREFIX}/core/bin/"* 2>/dev/null || true

rc-update add nginx default 2>/dev/null || true
rc-update add adaan-api default 2>/dev/null || true
rc-update add adaan-ui default 2>/dev/null || true

rc-service adaan-api restart || rc-service adaan-api start
rc-service adaan-ui restart || rc-service adaan-ui start
rc-service nginx restart || rc-service nginx start

echo "==> Demo install complete"
echo "    UI:  http://$(hostname -i 2>/dev/null || echo '<pi-ip>')/"
echo "    API: http://$(hostname -i 2>/dev/null || echo '<pi-ip>')/api/docs"
