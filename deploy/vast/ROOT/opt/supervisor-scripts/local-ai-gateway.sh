#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=local-ai-common.sh
source "${script_dir}/local-ai-common.sh"

load_vast_runtime
wait_for_provisioning

api_token="${LOCAL_AI_API_TOKEN:-${OPEN_BUTTON_TOKEN:-}}"
if (( ${#api_token} < 32 )); then
  printf 'OPEN_BUTTON_TOKEN or LOCAL_AI_API_TOKEN is required and must be at least 32 characters\n' >&2
  exit 2
fi

gateway_token_file="${GATEWAY_TOKEN_FILE:-/run/local-ai/gateway-token}"
command=(
  /opt/local-ai/.venv/bin/uvicorn
  local_ai_lab.gateway.app:create_app_from_env
  --factory
  --host 127.0.0.1
  --port 18000
  --no-access-log
)

if [[ "${1:-}" == "--dry-run" ]]; then
  print_command "${command[@]}"
  exit 0
fi

write_token_file "${gateway_token_file}" "${api_token}"
unset api_token OPEN_BUTTON_TOKEN LOCAL_AI_API_TOKEN

export GATEWAY_AUTH_MODE=token
export GATEWAY_TOKEN_FILE="${gateway_token_file}"
export GATEWAY_LLM_URL="${GATEWAY_LLM_URL:-http://127.0.0.1:8000}"
export GATEWAY_EMBEDDING_URL="${GATEWAY_EMBEDDING_URL:-http://127.0.0.1:8001}"
export GATEWAY_ALLOWED_MEDIA_DOMAINS="${VLLM_ALLOWED_MEDIA_DOMAIN:-qianwen-res.oss-cn-beijing.aliyuncs.com}"

if [[ "${LOCAL_AI_SKIP_DEPENDENCY_WAIT:-0}" != "1" ]]; then
  wait_for_http \
    "${GATEWAY_LLM_URL}/health" \
    "${MODEL_STARTUP_TIMEOUT_SECONDS:-1800}" \
    llm
  wait_for_http \
    "${GATEWAY_EMBEDDING_URL}/health" \
    "${MODEL_STARTUP_TIMEOUT_SECONDS:-1800}" \
    embedding
fi

exec "${command[@]}"
