#!/usr/bin/env bash
set -euo pipefail

admin_password="$(tr -d '\r\n' </run/secrets/keycloak_admin_password)"
db_password="$(tr -d '\r\n' </run/secrets/keycloak_db_password)"
if [[ ${#admin_password} -lt 32 || ${#db_password} -lt 32 ]]; then
  printf 'Keycloak secrets must contain at least 32 characters\n' >&2
  exit 2
fi

export KC_BOOTSTRAP_ADMIN_USERNAME=admin
export KC_BOOTSTRAP_ADMIN_PASSWORD="${admin_password}"
export KC_DB_PASSWORD="${db_password}"
exec /opt/keycloak/bin/kc.sh start-dev --import-realm
