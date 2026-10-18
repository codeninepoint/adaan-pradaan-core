#!/bin/sh
# Build demo artifacts for Raspberry Pi OS (Debian glibc) by default.
#   ./package-all.sh --docker              # gnu (RPi OS)
#   ./package-all.sh --docker --libc musl  # Alpine
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
DEPLOY_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
CORE_ROOT="$(CDPATH= cd -- "${DEPLOY_ROOT}/../.." && pwd)"
OUT_DIR="${OUT_DIR:-${CORE_ROOT}/dist}"
DOCKER_FLAGS=""
LIBC="gnu"

while [ $# -gt 0 ]; do
	case "$1" in
		--docker) DOCKER_FLAGS="--docker"; shift ;;
		--libc) LIBC="${2:-}"; shift 2 ;;
		--out) OUT_DIR="${2:-}"; shift 2 ;;
		*) echo "Unknown arg: $1" >&2; exit 1 ;;
	esac
done

mkdir -p "${OUT_DIR}"
export OUT_DIR

if [ -z "${DOCKER_FLAGS}" ]; then
	echo "Note: building without --docker uses this host arch/libc."
	echo "      For Pi artifacts, re-run with --docker --libc gnu"
fi

"${SCRIPT_DIR}/package-core.sh" ${DOCKER_FLAGS} --libc "${LIBC}"
"${SCRIPT_DIR}/package-ui.sh" ${DOCKER_FLAGS} --libc "${LIBC}"
"${SCRIPT_DIR}/package-ops.sh"

cp "${DEPLOY_ROOT}/install-demo.sh" "${OUT_DIR}/install-demo.sh"
chmod +x "${OUT_DIR}/install-demo.sh"

cd "${OUT_DIR}"
: > SHA256SUMS
for f in \
	adaan-pradaan-core-linux-aarch64-"${LIBC}".tar.gz \
	adan-pradan-ui-standalone-linux-aarch64-"${LIBC}".tar.gz \
	adaan-demo-pi-ops.tar.gz \
	install-demo.sh
do
	if [ -f "${f}" ]; then
		sha256sum "${f}" >> SHA256SUMS
	fi
done

echo "==> Artifacts in ${OUT_DIR}"
ls -lh "${OUT_DIR}"
cat SHA256SUMS
