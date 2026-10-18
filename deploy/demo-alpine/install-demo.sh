#!/bin/sh
# Download Adaan demo release assets and install on Raspberry Pi.
# Supports:
#   - Raspberry Pi OS / Debian (apt + systemd)  ← your Pi
#   - Alpine Linux (apk + OpenRC)
#
# Usage:
#   sudo ./install-demo.sh --repo OWNER/REPO --version demo-0.1.2
#   sudo ./install-demo.sh --base-url https://github.com/OWNER/REPO/releases/download/demo-0.1.2
set -eu

REPO=""
VERSION=""
BASE_URL=""
PREFIX="/opt/adaan"
ENV_DIR="/etc/adaan"

usage() {
	sed -n '2,10p' "$0" | tr -d '#'
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
		echo "Re-run as root (sudo ./install-demo.sh ...)." >&2
		exit 1
	fi
}

detect_os() {
	if command -v apk >/dev/null 2>&1 || [ -f /etc/alpine-release ]; then
		OS=alpine
		LIBC=musl
	elif command -v apt-get >/dev/null 2>&1; then
		OS=debian
		LIBC=gnu
	else
		echo "Unsupported OS: need Debian/Raspberry Pi OS (apt) or Alpine (apk)." >&2
		exit 1
	fi
	echo "==> Detected OS=${OS} libc=${LIBC}"
}

ensure_postgres_role() {
	su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='tenant'\"" 2>/dev/null | grep -q 1 \
		|| su - postgres -c "psql -c \"CREATE USER tenant WITH PASSWORD 'tenant';\""
	su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='tenant_platform'\"" 2>/dev/null | grep -q 1 \
		|| su - postgres -c "psql -c \"CREATE DATABASE tenant_platform OWNER tenant;\""
}

need_root
detect_os

CORE_TGZ="adaan-pradaan-core-linux-aarch64-${LIBC}.tar.gz"
UI_TGZ="adan-pradan-ui-standalone-linux-aarch64-${LIBC}.tar.gz"
OPS_TGZ="adaan-demo-pi-ops.tar.gz"

if [ "${OS}" = "debian" ]; then
	echo "==> Installing Debian/Raspberry Pi OS packages"
	export DEBIAN_FRONTEND=noninteractive
	apt-get update -qq
	apt-get install -y -qq nginx postgresql postgresql-contrib curl tar gzip ca-certificates

	# Node 18+ required for Next standalone
	if ! command -v node >/dev/null 2>&1; then
		apt-get install -y -qq nodejs
	fi
	NODE_MAJOR="$(node -p "process.versions.node.split('.')[0]" 2>/dev/null || echo 0)"
	if [ "${NODE_MAJOR}" -lt 18 ]; then
		echo "Node ${NODE_MAJOR} is too old; installing Node 22 from NodeSource"
		curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
		apt-get install -y -qq nodejs
	fi

	echo "==> Ensuring Postgres is running"
	systemctl enable --now postgresql

	echo "==> Ensuring DB role/database"
	ensure_postgres_role
else
	echo "==> Installing Alpine packages"
	apk add --no-cache nginx postgresql postgresql-contrib nodejs curl tar gzip coreutils

	echo "==> Ensuring Postgres is running"
	if command -v postgresql-setup >/dev/null 2>&1; then
		postgresql-setup --initdb || true
	elif [ -x /etc/init.d/postgresql ]; then
		rc-service postgresql setup 2>/dev/null || true
	fi
	rc-update add postgresql default 2>/dev/null || true
	rc-service postgresql start || true

	echo "==> Ensuring DB role/database"
	ensure_postgres_role
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT
cd "${WORKDIR}"

echo "==> Downloading from ${BASE_URL}"
curl -fsSLO "${BASE_URL}/${CORE_TGZ}"
curl -fsSLO "${BASE_URL}/${UI_TGZ}"
curl -fsSLO "${BASE_URL}/${OPS_TGZ}"
curl -fsSLO "${BASE_URL}/SHA256SUMS"
# Verify only the files we downloaded (Release may list both libc variants)
grep -E " (${CORE_TGZ}|${UI_TGZ}|${OPS_TGZ}|install-demo\\.sh)\$" SHA256SUMS > SHA256SUMS.local
sha256sum -c SHA256SUMS.local

echo "==> Unpacking to ${PREFIX}"
mkdir -p "${PREFIX}" "${ENV_DIR}"
tar -xzf "${CORE_TGZ}" -C "${PREFIX}"
tar -xzf "${UI_TGZ}" -C "${PREFIX}"
tar -xzf "${OPS_TGZ}" -C "${WORKDIR}"

if [ -d "${PREFIX}/adaan-pradaan-core" ] && [ ! -d "${PREFIX}/core" ]; then
	mv "${PREFIX}/adaan-pradaan-core" "${PREFIX}/core"
fi
if [ -d "${PREFIX}/adan-pradan-ui" ] && [ ! -d "${PREFIX}/ui" ]; then
	mv "${PREFIX}/adan-pradan-ui" "${PREFIX}/ui"
fi

OPS_DIR="${WORKDIR}/adaan-demo-pi"
if [ ! -d "${OPS_DIR}" ]; then
	OPS_DIR="$(find "${WORKDIR}" -maxdepth 2 -type d \( -name 'adaan-demo-pi' -o -name 'adaan-demo-alpine' \) | head -n1)"
fi

if [ ! -f "${ENV_DIR}/core.env" ]; then
	cp "${OPS_DIR}/config/demo.env.example" "${ENV_DIR}/core.env"
	echo "Wrote ${ENV_DIR}/core.env — edit TENANT_JWT_SECRET and TENANT_CORS_ORIGINS"
fi

chmod +x "${PREFIX}/core/bin/"* 2>/dev/null || true

if [ "${OS}" = "debian" ]; then
	cp "${OPS_DIR}/nginx/adaan.conf" /etc/nginx/sites-available/adaan
	ln -sfn /etc/nginx/sites-available/adaan /etc/nginx/sites-enabled/adaan
	rm -f /etc/nginx/sites-enabled/default

	cp "${OPS_DIR}/systemd/adaan-api.service" /etc/systemd/system/adaan-api.service
	cp "${OPS_DIR}/systemd/adaan-ui.service" /etc/systemd/system/adaan-ui.service
	systemctl daemon-reload
	systemctl enable --now adaan-api adaan-ui nginx
	systemctl restart adaan-api adaan-ui nginx
else
	cp "${OPS_DIR}/nginx/adaan.conf" /etc/nginx/http.d/adaan.conf
	cp "${OPS_DIR}/openrc/adaan-api" /etc/init.d/adaan-api
	cp "${OPS_DIR}/openrc/adaan-ui" /etc/init.d/adaan-ui
	chmod +x /etc/init.d/adaan-api /etc/init.d/adaan-ui
	rc-update add nginx default 2>/dev/null || true
	rc-update add adaan-api default 2>/dev/null || true
	rc-update add adaan-ui default 2>/dev/null || true
	rc-service adaan-api restart || rc-service adaan-api start
	rc-service adaan-ui restart || rc-service adaan-ui start
	rc-service nginx restart || rc-service nginx start
fi

PI_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "==> Demo install complete (${OS})"
echo "    UI:  http://${PI_IP:-<pi-ip>}/"
echo "    API: http://${PI_IP:-<pi-ip>}/api/docs"
echo "    Edit ${ENV_DIR}/core.env then: systemctl restart adaan-api   # (Debian)"
