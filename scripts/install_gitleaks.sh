#!/usr/bin/env bash
set -euo pipefail

GITLEAKS_VERSION="8.29.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INSTALL_DIR="${DEMO_DIR}/.tools/bin"

case "$(uname -s):$(uname -m)" in
  Darwin:arm64)
    ARCHIVE="gitleaks_${GITLEAKS_VERSION}_darwin_arm64.tar.gz"
    EXPECTED_SHA256="e85fa832ea341fb05485bf483e55e9d421f473348f0ede51b5212e0e5c19b7c4"
    ;;
  Linux:x86_64)
    ARCHIVE="gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz"
    EXPECTED_SHA256="39e07ad810336fd0ae80d0bd61c60d0521f628173e7583583b5df4a38738522c"
    ;;
  *)
    echo "unsupported platform: $(uname -s) $(uname -m)" >&2
    exit 2
    ;;
esac

if [[ "${1:-}" == "--check" ]]; then
  "${INSTALL_DIR}/gitleaks" version | grep -F "${GITLEAKS_VERSION}" >/dev/null
  exit 0
fi

DOWNLOAD_URL="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/${ARCHIVE}"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TEMP_DIR}"' EXIT

curl --fail --location --proto '=https' --tlsv1.2 "${DOWNLOAD_URL}" -o "${TEMP_DIR}/${ARCHIVE}"
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA256="$(sha256sum "${TEMP_DIR}/${ARCHIVE}" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA256="$(shasum -a 256 "${TEMP_DIR}/${ARCHIVE}" | awk '{print $1}')"
else
  echo "sha256sum or shasum is required" >&2
  exit 2
fi
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
  echo "checksum mismatch for ${ARCHIVE}" >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}"
tar -xzf "${TEMP_DIR}/${ARCHIVE}" -C "${TEMP_DIR}" gitleaks
install -m 0755 "${TEMP_DIR}/gitleaks" "${INSTALL_DIR}/gitleaks"
"${INSTALL_DIR}/gitleaks" version
