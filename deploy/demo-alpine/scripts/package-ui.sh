#!/bin/sh
# Build Next.js standalone tarball for aarch64.
#   --libc gnu   → Debian / Raspberry Pi OS (node:22 bookworm)  [default]
#   --libc musl  → Alpine (node:22-alpine)
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
DEPLOY_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
CORE_ROOT="$(CDPATH= cd -- "${DEPLOY_ROOT}/../.." && pwd)"
OUT_DIR="${OUT_DIR:-${CORE_ROOT}/dist}"
ARCH="${ARCH:-$(uname -m)}"
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-/api}"
LIBC="${LIBC:-gnu}"
USE_DOCKER=0

resolve_ui_app() {
	if [ -n "${UI_APP:-}" ] && [ -f "${UI_APP}/package.json" ]; then
		return 0
	fi
	if [ -f "${CORE_ROOT}/adan-pradan-ui/app/package.json" ]; then
		UI_APP="${CORE_ROOT}/adan-pradan-ui/app"
		return 0
	fi
	if [ -f "${CORE_ROOT}/../adan-pradan-ui/app/package.json" ]; then
		UI_APP="$(CDPATH= cd -- "${CORE_ROOT}/../adan-pradan-ui/app" && pwd)"
		return 0
	fi
	return 1
}

while [ $# -gt 0 ]; do
	case "$1" in
		--docker) USE_DOCKER=1; shift ;;
		--out) OUT_DIR="${2:-}"; shift 2 ;;
		--api-url) NEXT_PUBLIC_API_URL="${2:-}"; shift 2 ;;
		--libc) LIBC="${2:-}"; shift 2 ;;
		*) echo "Unknown arg: $1" >&2; exit 1 ;;
	esac
done

case "${LIBC}" in
	gnu|musl) ;;
	*) echo "LIBC must be gnu or musl" >&2; exit 1 ;;
esac

if ! resolve_ui_app; then
	echo "UI app not found. Checkout adan-pradan-ui next to core, or set UI_APP." >&2
	exit 1
fi

DOCKER_ROOT="${CORE_ROOT}"
DOCKER_SCRIPT="/workspace/deploy/demo-alpine/scripts/package-ui.sh"
case "${UI_APP}" in
	"${CORE_ROOT}"/*) ;;
	*)
		DOCKER_ROOT="$(CDPATH= cd -- "${CORE_ROOT}/.." && pwd)"
		DOCKER_SCRIPT="/workspace/adaan-pradaan-core/deploy/demo-alpine/scripts/package-ui.sh"
		;;
esac

if [ "${USE_DOCKER}" -eq 1 ]; then
	mkdir -p "${CORE_ROOT}/dist"
	if [ "${DOCKER_ROOT}" = "${CORE_ROOT}" ]; then
		DOCKER_OUT=/workspace/dist
	else
		DOCKER_OUT=/workspace/adaan-pradaan-core/dist
	fi
	if [ "${LIBC}" = "musl" ]; then
		IMAGE="node:22-alpine"
	else
		IMAGE="node:22-bookworm"
	fi
	docker run --rm --platform linux/arm64 \
		-v "${DOCKER_ROOT}:/workspace" \
		-w /workspace \
		-e OUT_DIR="${DOCKER_OUT}" \
		-e NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL}" \
		-e LIBC="${LIBC}" \
		"${IMAGE}" \
		sh "${DOCKER_SCRIPT}" --libc "${LIBC}"
	exit $?
fi

echo "==> Packaging UI from ${UI_APP} (API_URL=${NEXT_PUBLIC_API_URL} libc=${LIBC})"

if command -v apk >/dev/null 2>&1; then
	apk add --no-cache bash tar gzip libc6-compat
elif command -v apt-get >/dev/null 2>&1; then
	export DEBIAN_FRONTEND=noninteractive
	apt-get update -qq
	apt-get install -y -qq tar gzip ca-certificates
fi

cd "${UI_APP}"

if ! command -v pnpm >/dev/null 2>&1; then
	if command -v corepack >/dev/null 2>&1; then
		corepack enable 2>/dev/null || true
		corepack prepare pnpm@11.24.0 --activate 2>/dev/null || true
	fi
fi

if command -v pnpm >/dev/null 2>&1; then
	pnpm install --frozen-lockfile
	NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL}" NEXT_TELEMETRY_DISABLED=1 pnpm build
elif [ -f pnpm-lock.yaml ] && command -v npx >/dev/null 2>&1; then
	npx --yes pnpm@11.24.0 install --frozen-lockfile
	NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL}" NEXT_TELEMETRY_DISABLED=1 npx --yes pnpm@11.24.0 build
else
	npm ci
	NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL}" NEXT_TELEMETRY_DISABLED=1 npm run build
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
PKG="${STAGE}/ui"
mkdir -p "${PKG}"

STANDALONE="${UI_APP}/.next/standalone"
if [ -d "${STANDALONE}/app" ]; then
	cp -a "${STANDALONE}/app/." "${PKG}/"
elif [ -f "${STANDALONE}/server.js" ]; then
	cp -a "${STANDALONE}/." "${PKG}/"
else
	NEST="$(find "${STANDALONE}" -name server.js -type f | head -n1)"
	if [ -z "${NEST}" ]; then
		echo "standalone server.js not found under ${STANDALONE}" >&2
		exit 1
	fi
	cp -a "$(dirname "${NEST}")/." "${PKG}/"
fi

mkdir -p "${PKG}/.next"
cp -a "${UI_APP}/.next/static" "${PKG}/.next/static"
if [ -d "${UI_APP}/public" ]; then
	cp -a "${UI_APP}/public" "${PKG}/public"
fi

case "${ARCH}" in
	aarch64|arm64) ASSET_ARCH="aarch64" ;;
	x86_64|amd64) ASSET_ARCH="x86_64" ;;
	*) ASSET_ARCH="${ARCH}" ;;
esac

mkdir -p "${OUT_DIR}"
TGZ="${OUT_DIR}/adan-pradan-ui-standalone-linux-${ASSET_ARCH}-${LIBC}.tar.gz"
tar -czf "${TGZ}" -C "${STAGE}" ui
echo "Wrote ${TGZ}"
ls -lh "${TGZ}"
