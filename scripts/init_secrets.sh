#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
secret_dir="${repo_dir}/secrets"

umask 077
mkdir -p "${secret_dir}"

create_secret() {
  local path="$1"
  if [[ -e "${path}" ]]; then
    printf 'refusing to overwrite existing secret: %s\n' "${path}" >&2
    return 1
  fi
  openssl rand -hex 32 >"${path}"
  chmod 600 "${path}"
}

create_secret "${secret_dir}/gateway-token"
create_secret "${secret_dir}/grafana-admin-password"
create_secret "${secret_dir}/keycloak-admin-password"
create_secret "${secret_dir}/keycloak-db-password"
printf 'created four private secret files in %s\n' "${secret_dir}"
