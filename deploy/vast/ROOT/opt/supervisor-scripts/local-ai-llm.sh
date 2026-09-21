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

llm_model="${LLM_MODEL:-Qwen/Qwen3-VL-8B-Instruct}"
llm_revision="${LLM_REVISION:-0c351dd01ed87e9c1b53cbc748cba10e6187ff3b}"
llm_served_name="${LLM_SERVED_NAME:-local-vision-language}"
llm_dtype="${LLM_DTYPE:-bfloat16}"
llm_max_model_len="${LLM_MAX_MODEL_LEN:-8192}"
llm_gpu_fraction="${LLM_GPU_MEMORY_UTILIZATION:-0.72}"
llm_max_num_seqs="${LLM_MAX_NUM_SEQS:-4}"
llm_tensor_parallel_size="${LLM_TENSOR_PARALLEL_SIZE:-1}"
llm_max_images="${LLM_MAX_IMAGES_PER_PROMPT:-2}"
allowed_media_domains="${VLLM_ALLOWED_MEDIA_DOMAIN:-qianwen-res.oss-cn-beijing.aliyuncs.com}"

command=(
  vllm serve "${llm_model}"
  --revision "${llm_revision}"
  --served-model-name "${llm_served_name}"
  --dtype "${llm_dtype}"
  --max-model-len "${llm_max_model_len}"
  --gpu-memory-utilization "${llm_gpu_fraction}"
  --max-num-seqs "${llm_max_num_seqs}"
  --tensor-parallel-size "${llm_tensor_parallel_size}"
  --limit-mm-per-prompt "image=${llm_max_images}"
  --allowed-media-domains "${allowed_media_domains}"
  --host 127.0.0.1
  --port 8000
)

if [[ "${1:-}" == "--dry-run" ]]; then
  print_command "${command[@]}"
  exit 0
fi

if [[ "${LOCAL_AI_SKIP_DEPENDENCY_WAIT:-0}" != "1" ]]; then
  wait_for_http \
    http://127.0.0.1:8001/health \
    "${MODEL_STARTUP_TIMEOUT_SECONDS:-1800}" \
    embedding
fi

exec "${command[@]}"
