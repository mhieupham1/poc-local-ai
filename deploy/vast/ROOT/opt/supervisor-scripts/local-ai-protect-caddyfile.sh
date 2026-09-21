#!/usr/bin/env bash
set -euo pipefail

caddyfile="${1:-/etc/Caddyfile}"
if [[ ! -f "${caddyfile}" ]]; then
  printf 'Caddyfile is missing or is not a regular file: %s\n' "${caddyfile}" >&2
  exit 1
fi

chmod 600 "${caddyfile}"
