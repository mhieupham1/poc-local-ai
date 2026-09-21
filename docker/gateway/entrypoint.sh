#!/usr/bin/env sh
set -eu

if [ "${GATEWAY_AUTH_MODE:-token}" = "token" ]; then
  runtime_token=/tmp/gateway-token
  umask 077
  cp "${GATEWAY_TOKEN_FILE:-/run/secrets/gateway_token}" "${runtime_token}"
  chmod 600 "${runtime_token}"
  export GATEWAY_TOKEN_FILE="${runtime_token}"
fi

exec uvicorn local_ai_lab.gateway.app:create_app_from_env \
  --factory \
  --host 0.0.0.0 \
  --port 8080 \
  --no-access-log
