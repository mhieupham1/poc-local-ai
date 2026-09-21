#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=local-ai-common.sh
source "${script_dir}/local-ai-common.sh"

load_vast_runtime
activate_vllm_runtime
unset OPEN_BUTTON_TOKEN LOCAL_AI_API_TOKEN || true
wait_for_provisioning
if ! validate_fraction_budget; then
  exit 2
fi

embedding_model="${EMBEDDING_MODEL:-BAAI/bge-m3}"
embedding_revision="${EMBEDDING_REVISION:-5617a9f61b028005a4858fdac845db406aefb181}"
embedding_served_name="${EMBEDDING_SERVED_NAME:-BAAI/bge-m3}"
embedding_gpu_fraction="${EMBEDDING_GPU_MEMORY_UTILIZATION:-0.15}"

command=(
  vllm serve "${embedding_model}"
  --revision "${embedding_revision}"
  --served-model-name "${embedding_served_name}"
  --runner pooling
  --hf-overrides '{"architectures":["BgeM3EmbeddingModel"]}'
  --pooler-config.task embed
  --gpu-memory-utilization "${embedding_gpu_fraction}"
  --host 127.0.0.1
  --port 8001
)

if [[ "${1:-}" == "--dry-run" ]]; then
  print_command "${command[@]}"
  exit 0
fi

exec "${command[@]}"
