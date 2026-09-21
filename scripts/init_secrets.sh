#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
secret_dir="${repo_dir}/secrets"

if [[ "$(id -u)" -ne 0 ]]; then
  printf 'run this script as root (or with sudo) to provision service-owned secret files\n' >&2
  exit 1
fi

umask 077
mkdir -p "${secret_dir}"

create_secret() {
  local path="$1"
  local owner="$2"
  if [[ -e "${path}" || -L "${path}" ]]; then
    if [[ ! -f "${path}" || -L "${path}" ]]; then
      printf 'refusing non-regular secret path: %s\n' "${path}" >&2
      return 1
    fi
    printf 'preserving existing secret value: %s\n' "${path}"
  else
    openssl rand -hex 32 >"${path}"
  fi

  chown "${owner}" "${path}"
  chmod 600 "${path}"
}

create_secret "${secret_dir}/gateway-token" "10001:10001"
create_secret "${secret_dir}/grafana-admin-password" "472:0"
create_secret "${secret_dir}/keycloak-admin-password" "1000:0"
create_secret "${secret_dir}/keycloak-db-password" "0:0"
printf 'provisioned four private secret files in %s\n' "${secret_dir}"
