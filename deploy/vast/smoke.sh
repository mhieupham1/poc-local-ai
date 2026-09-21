#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'usage: %s --base-url https://host --token-file /path/to/token\n' "$0" >&2
  exit 2
}

base_url=''
token_file=''
while (( $# )); do
  case "$1" in
    --base-url)
      [[ $# -ge 2 ]] || usage
      base_url="$2"
      shift 2
      ;;
    --token-file)
      [[ $# -ge 2 ]] || usage
      token_file="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done

if [[ ! "${base_url}" =~ ^https://[^/?#]+/?$ ]]; then
  printf 'base URL must use https and contain no path, query, or fragment\n' >&2
  exit 2
fi
base_url="${base_url%/}"

if [[ ! -f "${token_file}" ]]; then
  printf 'token file does not exist or is not a regular file\n' >&2
  exit 2
fi

if token_mode="$(stat -c '%a' "${token_file}" 2>/dev/null)"; then
  :
else
  token_mode="$(stat -f '%Lp' "${token_file}")"
fi
if [[ "${token_mode}" != "600" ]]; then
  printf 'token file must have mode 0600; got %s\n' "${token_mode}" >&2
  exit 2
fi

token="$(tr -d '\r\n' <"${token_file}")"
if [[ ! "${token}" =~ ^[A-Za-z0-9._~-]{32,}$ ]]; then
  printf 'token must be at least 32 URL-safe characters\n' >&2
  exit 2
fi

temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/local-ai-smoke.XXXXXX")"
cleanup() {
  token=''
  rm -rf -- "${temp_dir}"
}
trap cleanup EXIT INT TERM

curl_config="${temp_dir}/curl.conf"
anonymous_curl_config="${temp_dir}/anonymous-curl.conf"
invalid_curl_config="${temp_dir}/invalid-curl.conf"
umask 077
{
  printf 'header = "Authorization: Bearer %s"\n' "${token}"
  printf 'header = "Content-Type: application/json"\n'
} >"${curl_config}"
printf 'header = "Content-Type: application/json"\n' >"${anonymous_curl_config}"
{
  printf '%s\n' \
    'header = "Authorization: Bearer invalid-token-for-smoke-check-00000000"' \
    'header = "Content-Type: application/json"'
} >"${invalid_curl_config}"
chmod 600 "${curl_config}"
chmod 600 "${anonymous_curl_config}" "${invalid_curl_config}"
token=''

cat >"${temp_dir}/chat.json" <<'JSON'
{"model":"local-vision-language","messages":[{"role":"user","content":"Trả lời đúng một từ: chào"}],"max_tokens":32,"stream":false}
JSON
cat >"${temp_dir}/embedding.json" <<'JSON'
{"model":"BAAI/bge-m3","input":["xin chào"]}
JSON
cat >"${temp_dir}/vision.json" <<'JSON'
{"model":"local-vision-language","messages":[{"role":"user","content":[{"type":"text","text":"Mô tả ngắn gọn ảnh này."},{"type":"image_url","image_url":{"url":"https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen-VL/assets/demo.jpeg"}}]}],"max_tokens":64,"stream":false}
JSON

curl_bin="${CURL_BIN:-curl}"
curl_args=(--config "${curl_config}" --fail-with-body --silent --show-error)

expect_unauthorized() {
  local config_file="$1"
  local output_file="$2"
  local status
  status="$(
    "${curl_bin}" \
      --config "${config_file}" \
      --silent \
      --show-error \
      --output "${output_file}" \
      --write-out '%{http_code}' \
      --request GET \
      "${base_url}/v1/models"
  )"
  if [[ "${status}" != "401" ]]; then
    printf 'authentication check expected HTTP 401; got %s\n' "${status}" >&2
    return 1
  fi
}

expect_unauthorized "${anonymous_curl_config}" "${temp_dir}/missing-auth.json"
expect_unauthorized "${invalid_curl_config}" "${temp_dir}/invalid-auth.json"
"${curl_bin}" "${curl_args[@]}" \
  --output "${temp_dir}/ready.json" \
  --request GET \
  "${base_url}/readyz"
"${curl_bin}" "${curl_args[@]}" \
  --output "${temp_dir}/chat-response.json" \
  --request POST \
  --data-binary "@${temp_dir}/chat.json" \
  "${base_url}/v1/chat/completions"
"${curl_bin}" "${curl_args[@]}" \
  --output "${temp_dir}/vision-response.json" \
  --request POST \
  --data-binary "@${temp_dir}/vision.json" \
  "${base_url}/v1/chat/completions"
"${curl_bin}" "${curl_args[@]}" \
  --output "${temp_dir}/embedding-response.json" \
  --request POST \
  --data-binary "@${temp_dir}/embedding.json" \
  "${base_url}/v1/embeddings"

python3 - \
  "${temp_dir}/ready.json" \
  "${temp_dir}/chat-response.json" \
  "${temp_dir}/vision-response.json" \
  "${temp_dir}/embedding-response.json" <<'PY'
import json
import sys
from pathlib import Path

ready = json.loads(Path(sys.argv[1]).read_text())
chat = json.loads(Path(sys.argv[2]).read_text())
vision = json.loads(Path(sys.argv[3]).read_text())
embedding = json.loads(Path(sys.argv[4]).read_text())

if ready.get("status") != "ready":
    raise SystemExit("gateway readiness response is not ready")
if not isinstance(chat.get("choices"), list) or not chat["choices"]:
    raise SystemExit("chat response has no choices")
if not isinstance(vision.get("choices"), list) or not vision["choices"]:
    raise SystemExit("vision response has no choices")
data = embedding.get("data")
if not isinstance(data, list) or not data or not isinstance(data[0].get("embedding"), list):
    raise SystemExit("embedding response has no vector")

print("auth: ok")
print("ready: ok")
print("chat: ok")
print("vision: ok")
print("embedding: ok")
PY
