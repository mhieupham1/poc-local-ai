#!/usr/bin/env bash

# This is the wrapper shipped by the pinned Vast base image with two security
# additions: redact generated credentials before they reach the portal log and
# restrict the generated Caddyfile because it contains authentication secrets.
utils=/opt/supervisor-scripts/utils
# shellcheck source=/dev/null
. "${utils}/logging.sh" ""
# shellcheck source=/dev/null
. "${utils}/cleanup_generic.sh"
# shellcheck source=/dev/null
. "${utils}/environment.sh"
# shellcheck source=/dev/null
. "${utils}/exit_serverless.sh"

umask 077
if [[ -f /etc/Caddyfile ]]; then
  /opt/supervisor-scripts/local-ai-protect-caddyfile.sh /etc/Caddyfile || exit 1
fi

cd /opt/portal-aio/caddy_manager || exit 1
/opt/portal-aio/venv/bin/python caddy_config_manager.py 2>&1 \
  | /opt/supervisor-scripts/local-ai-redact-caddy-output.sh

if [[ ! -s /etc/portal.yaml ]]; then
  if [[ -n "${PORTAL_CONFIG:-}" ]]; then
    printf '%s\n' \
      'ERROR: PORTAL_CONFIG is set but caddy_config_manager.py produced no' \
      '  /etc/portal.yaml. Not publishing an empty config.' >&2
  else
    printf 'applications: {}\n' >/etc/portal.yaml
  fi
fi

if [[ -f /etc/Caddyfile ]]; then
  /opt/supervisor-scripts/local-ai-protect-caddyfile.sh /etc/Caddyfile || exit 1
  printf '%s\n' 'Starting Caddy...'
  /opt/portal-aio/caddy_manager/caddy run --config /etc/Caddyfile 2>&1
  exit $?
fi

printf '%s\n' 'Skipping Caddy startup - No config file was generated'
