#!/bin/sh
# Build all demo artifacts into dist/ (use --docker for Pi aarch64 musl).
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
DEPLOY_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"
CORE_ROOT="$(CDPATH= cd -- "${DEPLOY_ROOT}/../.." && pwd)"
OUT_DIR="${OUT_DIR:-${CORE_ROOT}/dist}"
DOCKER_FLAGS=""

while [ $# -gt 0 ]; do
	case "$1" in
		--docker) DOCKER_FLAGS="--docker"; shift ;;
		--out) OUT_DIR="${2:-}"; shift 2 ;;
		*) echo "Unknown arg: $1" >&2; exit 1 ;;
	esac
done

mkdir -p "${OUT_DIR}"
export OUT_DIR

if [ -z "${DOCKER_FLAGS}" ]; then
	echo "Note: building without --docker uses this host arch/libc."
	echo "      For Raspberry Pi Alpine aarch64 musl artifacts, re-run with --docker."
fi

"${SCRIPT_DIR}/package-core.sh" ${DOCKER_FLAGS}
"${SCRIPT_DIR}/package-ui.sh" ${DOCKER_FLAGS}
"${SCRIPT_DIR}/package-ops.sh"

cp "${DEPLOY_ROOT}/install-demo.sh" "${OUT_DIR}/install-demo.sh"
chmod +x "${OUT_DIR}/install-demo.sh"

cd "${OUT_DIR}"
: > SHA256SUMS
for f in \
	adaan-pradaan-core-linux-aarch64-musl.tar.gz \
	adan-pradan-ui-standalone-linux-aarch64.tar.gz \
	adaan-demo-alpine-openrc.tar.gz \
	install-demo.sh
do
	if [ -f "${f}" ]; then
		sha256sum "${f}" >> SHA256SUMS
	fi
done
for f in adaan-pradaan-core-linux-*-musl.tar.gz adan-pradan-ui-standalone-linux-*.tar.gz; do
	[ -f "${f}" ] || continue
	grep -q " ${f}\$" SHA256SUMS 2>/dev/null && continue
	sha256sum "${f}" >> SHA256SUMS
done

echo "==> Artifacts in ${OUT_DIR}"
ls -lh "${OUT_DIR}"
cat SHA256SUMS
