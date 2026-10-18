#!/bin/sh
# Pack nginx + OpenRC + env + install helpers for Alpine demo.
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
DEPLOY_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
CORE_ROOT="$(CDPATH= cd -- "${DEPLOY_ROOT}/../.." && pwd)"
OUT_DIR="${OUT_DIR:-${CORE_ROOT}/dist}"

while [ $# -gt 0 ]; do
	case "$1" in
		--out) OUT_DIR="${2:-}"; shift 2 ;;
		*) echo "Unknown arg: $1" >&2; exit 1 ;;
	esac
done

STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
PKG="${STAGE}/adaan-demo-alpine"
mkdir -p "${PKG}"

cp -a "${DEPLOY_ROOT}/nginx" "${PKG}/nginx"
cp -a "${DEPLOY_ROOT}/openrc" "${PKG}/openrc"
cp -a "${DEPLOY_ROOT}/config" "${PKG}/config"
cp "${DEPLOY_ROOT}/INSTALL.md" "${PKG}/INSTALL.md"
cp "${DEPLOY_ROOT}/README.md" "${PKG}/README.md"
cp "${DEPLOY_ROOT}/install-demo.sh" "${PKG}/install-demo.sh"
chmod +x "${PKG}/install-demo.sh" "${PKG}/openrc/"*

mkdir -p "${OUT_DIR}"
TGZ="${OUT_DIR}/adaan-demo-alpine-openrc.tar.gz"
tar -czf "${TGZ}" -C "${STAGE}" adaan-demo-alpine
echo "Wrote ${TGZ}"
ls -lh "${TGZ}"
