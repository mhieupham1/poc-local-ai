#!/usr/bin/env bash
set -euo pipefail

validate_fraction_budget() {
  python3 - "${LLM_GPU_MEMORY_UTILIZATION:-0.72}" \
    "${EMBEDDING_GPU_MEMORY_UTILIZATION:-0.15}" <<'PY'
import sys

try:
    llm, embedding = map(float, sys.argv[1:])
except ValueError as exc:
    raise SystemExit("GPU memory utilization values must be numbers") from exc

if not (0 < llm < 1 and 0 < embedding < 1 and llm + embedding <= 0.90):
    raise SystemExit("combined GPU memory utilization must be <= 0.90")
PY
}

load_vast_runtime() {
  if [[ "${LOCAL_AI_SKIP_VAST_UTILS:-0}" == "1" ]]; then
    return
  fi

  local utils="${VAST_UTILS_DIR:-/opt/supervisor-scripts/utils}"
  local restore_nounset=0
  if [[ $- == *u* ]]; then
    restore_nounset=1
    set +u
  fi
  # shellcheck source=/dev/null
  source "${utils}/logging.sh" ""
  # shellcheck source=/dev/null
  source "${utils}/cleanup_generic.sh"
  # shellcheck source=/dev/null
  source "${utils}/environment.sh"
  if (( restore_nounset )); then
    set -u
  fi
}

activate_vllm_runtime() {
  if [[ -f /venv/main/bin/activate ]]; then
    # shellcheck source=/dev/null
    source /venv/main/bin/activate
  fi
}

wait_for_provisioning() {
  while [[ -f /.provisioning ]]; do
    printf '%s startup paused until instance provisioning has completed\n' \
      "${PROC_NAME:-local-ai}"
    sleep 5
  done
}

wait_for_http() {
  local url="$1"
  local timeout_seconds="$2"
  local name="$3"
  local started="${SECONDS}"

  while ! curl --fail --silent --show-error --output /dev/null "${url}"; do
    if (( SECONDS - started >= timeout_seconds )); then
      printf 'timed out waiting for %s at %s\n' "${name}" "${url}" >&2
      return 1
    fi
    sleep 2
  done
}

print_command() {
  printf '%q ' "$@"
  printf '\n'
}

write_token_file() {
  local path="$1"
  local token="$2"
  local token_dir
  token_dir="$(dirname "${path}")"

  umask 077
  mkdir -p "${token_dir}"
  chmod 700 "${token_dir}"
  printf '%s' "${token}" >"${path}"
  chmod 600 "${path}"
}
