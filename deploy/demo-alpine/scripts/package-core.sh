#!/bin/sh
# Build Alpine musl aarch64 Core API tarball.
# Lives in adaan-pradaan-core/deploy/demo-alpine — CORE_SRC is the core repo root.
# Prefer: ./package-core.sh --docker
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
DEPLOY_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
CORE_ROOT="$(CDPATH= cd -- "${DEPLOY_ROOT}/../.." && pwd)"
CORE_SRC="${CORE_SRC:-${CORE_ROOT}}"
OUT_DIR="${OUT_DIR:-${CORE_ROOT}/dist}"
ARCH="${ARCH:-$(uname -m)}"
USE_DOCKER=0

while [ $# -gt 0 ]; do
	case "$1" in
		--docker) USE_DOCKER=1; shift ;;
		--out) OUT_DIR="${2:-}"; shift 2 ;;
		*) echo "Unknown arg: $1" >&2; exit 1 ;;
	esac
done

if [ "${USE_DOCKER}" -eq 1 ]; then
	mkdir -p "${OUT_DIR}"
	docker run --rm --platform linux/arm64 \
		-v "${CORE_ROOT}:/workspace" \
		-w /workspace \
		-e OUT_DIR=/workspace/dist \
		python:3.12-alpine \
		sh /workspace/deploy/demo-alpine/scripts/package-core.sh
	exit $?
fi

if [ ! -f "${CORE_SRC}/pyproject.toml" ]; then
	echo "Core project not found at ${CORE_SRC}" >&2
	exit 1
fi

echo "==> Packaging Core from ${CORE_SRC} (arch=${ARCH})"

if command -v apk >/dev/null 2>&1; then
	apk add --no-cache \
		python3 py3-pip python3-dev \
		gcc musl-dev libffi-dev openssl-dev \
		postgresql-dev cargo rust \
		bash tar gzip
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
PKG="${STAGE}/core"
mkdir -p "${PKG}/bin" "${PKG}/config"

cp -a "${CORE_SRC}/src" "${PKG}/src"
cp -a "${CORE_SRC}/migrations" "${PKG}/migrations"
cp "${CORE_SRC}/alembic.ini" "${PKG}/alembic.ini"
cp "${CORE_SRC}/pyproject.toml" "${PKG}/pyproject.toml"
cp "${CORE_SRC}/README.md" "${PKG}/README.md" 2>/dev/null || true
cp "${DEPLOY_ROOT}/bin/adaan-api" "${PKG}/bin/adaan-api"
cp "${DEPLOY_ROOT}/bin/adaan-migrate" "${PKG}/bin/adaan-migrate"
cp "${DEPLOY_ROOT}/config/demo.env.example" "${PKG}/config/demo.env.example"
chmod +x "${PKG}/bin/adaan-api" "${PKG}/bin/adaan-migrate"

python3 -m venv "${PKG}/.venv"
# shellcheck disable=SC1091
. "${PKG}/.venv/bin/activate"
pip install --upgrade pip wheel hatchling
(
	cd "${PKG}"
	pip install .
)

# Avoid uvloop on musl when possible (uvicorn falls back to asyncio)
pip uninstall -y uvloop httptools 2>/dev/null || true

deactivate

mkdir -p "${OUT_DIR}"
case "${ARCH}" in
	aarch64|arm64) ASSET_ARCH="aarch64" ;;
	x86_64|amd64) ASSET_ARCH="x86_64" ;;
	*) ASSET_ARCH="${ARCH}" ;;
esac
TGZ="${OUT_DIR}/adaan-pradaan-core-linux-${ASSET_ARCH}-musl.tar.gz"

tar -czf "${TGZ}" -C "${STAGE}" core
echo "Wrote ${TGZ}"
ls -lh "${TGZ}"
