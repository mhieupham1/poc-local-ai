#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${repo_dir}/config/gpu.env"

if [[ ! -f "${env_file}" ]]; then
  printf 'missing %s; copy config/gpu.env.example and review it first\n' "${env_file}" >&2
  exit 2
fi

cd "${repo_dir}"
uv run local-ai-lab stack validate --compose-file compose.yaml --env-file config/gpu.env
exec docker compose --env-file "${env_file}" -f compose.yaml "$@"
