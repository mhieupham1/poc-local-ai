# Local AI Inference Lab

PoC triển khai ba năng lực AI trên một GPU:

- LLM và Vision: `Qwen/Qwen3-VL-8B-Instruct`.
- Embedding: `BAAI/bge-m3`.
- Một API Gateway tương thích OpenAI, bắt buộc Bearer token.
- Benchmark TTFT, tokens/second, latency, concurrency và GPU/VRAM.

Sau khi hoàn thành hướng dẫn này, bạn có một HTTPS base URL:

```text
https://<host>/v1/chat/completions  -> text và Vision
https://<host>/v1/embeddings        -> embedding
```

## Hiểu đúng cách triển khai

Vast instance đã là một container. Không cài Docker, không `git clone` và không
chạy `docker compose` bên trong Vast.

```text
Máy cá nhân                 GitHub Container Registry             Vast.ai
clone source -> build image -> push image lên GHCR -> kéo image -> tự chạy AI
```

Bạn thao tác ở ba nơi:

| Nơi thao tác | Công việc |
|---|---|
| Máy cá nhân | Clone source, test, build/push image, smoke test và tải report |
| GitHub/GHCR | Chứa source và Docker image public |
| Vast.ai | Thuê GPU, tạo template, SSH kiểm tra và benchmark |

Thứ tự bắt buộc:

```text
Chuẩn bị source và workload
  -> test local
  -> build/push GHCR
  -> tạo Vast template
  -> thuê GPU
  -> smoke test 8K
  -> benchmark 8K
  -> thử 32K rồi 64K
  -> tải report
  -> Destroy instance
  -> dùng số liệu để chọn server vật lý
```

Không mua server vật lý trước khi có report từ GPU thuê. Cấu hình hiện tại đủ để
bắt đầu PoC inference, nhưng ứng dụng RAG giống NotebookLM là bước sau và chưa
được coi là hoàn thành chỉ vì ba API đã chạy.

## Trước khi bắt đầu

Bạn cần:

- Tài khoản GitHub và một Personal Access Token có quyền `write:packages`.
- Tài khoản Vast.ai đã nạp credit.
- Docker Desktop đang chạy trên máy cá nhân.
- Git, `uv`, `curl`, SSH và SCP.
- Một SSH key Ed25519 đã thêm vào Vast.ai.
- Chỉ dùng dữ liệu public/synthetic trên máy thuê ngoài.

Kiểm tra công cụ trên máy cá nhân:

```bash
git --version
uv --version
docker version
docker buildx version
curl --version
ssh -V
```

Nếu một lệnh bị thiếu, cài công cụ đó trước khi tiếp tục. Trên macOS có thể cài
Git và `uv` bằng Homebrew; Docker cần Docker Desktop. Không thuê GPU trước khi
hoàn thành bước build và push image.

## Bước 1 — clone source

Repository public của demo là `mhieupham1/poc-local-ai`. Nếu fork sang tài khoản
khác, chỉ cần thay biến `GITHUB_USER` bên dưới.

```bash
export GITHUB_USER=mhieupham1
export REPO_NAME=poc-local-ai

git clone "https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
cd "${REPO_NAME}"
```

Từ đây, tất cả lệnh trên máy cá nhân được chạy tại thư mục gốc repository này.
Nếu source đã có sẵn, chỉ cần `cd` vào thư mục chứa file README này.

## Bước 2 — kiểm tra source trước khi build

```bash
uv sync --dev
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src

docker buildx build \
  --check \
  --platform linux/amd64 \
  --file deploy/vast/Dockerfile \
  .
```

Chỉ tiếp tục khi tất cả lệnh trả về exit code `0`.

Các tài liệu benchmark tải về và workload sinh ra phải nằm ngoài Docker image:

```bash
git check-ignore benchmarks/sources/war-and-peace.en.txt
git check-ignore benchmarks/generated/war-and-peace-8192.jsonl
```

Hai lệnh phải in ra đường dẫn tương ứng. `.dockerignore` cũng loại toàn bộ
`benchmarks/sources` và `benchmarks/generated`; workload cần dùng trên Vast sẽ
được upload riêng bằng SCP.

## Bước 3 — đăng nhập GHCR, build và push image

Chọn một tag bất biến cho lần thử. Không push đè cùng một tag khi source thay
đổi.

```bash
export IMAGE_TAG=v0.1.0
export IMAGE_REF="ghcr.io/${GITHUB_USER}/poc-local-ai-vast"
```

Đăng nhập GHCR mà không để token xuất hiện trong shell history:

```bash
read -r -s -p "GitHub package token: " GHCR_TOKEN
printf '\n'
printf '%s' "${GHCR_TOKEN}" | \
  docker login ghcr.io --username "${GITHUB_USER}" --password-stdin
unset GHCR_TOKEN
```

Build image Linux x86-64 và push lên GHCR:

```bash
docker buildx build \
  --platform linux/amd64 \
  --file deploy/vast/Dockerfile \
  --tag "${IMAGE_REF}:${IMAGE_TAG}" \
  --push \
  .

docker buildx imagetools inspect "${IMAGE_REF}:${IMAGE_TAG}"
```

Ghi lại dòng `Digest: sha256:...` để biết chính xác image đã benchmark. Trong
GitHub, mở package vừa tạo rồi chọn:

```text
Package settings -> Change visibility -> Public
```

Vast sẽ không pull được image nếu GHCR package vẫn private và template không có
registry credential.

## Bước 4 — chuẩn bị SSH key

Nếu chưa có key dành cho Vast, tạo trên máy cá nhân:

```bash
ssh-keygen -t ed25519 -C "vast-ai-poc"
```

Chỉ đưa public key có đuôi `.pub` lên `Vast Console -> Account -> Keys`. Không
upload, commit hoặc gửi private key.

## Bước 5 — tạo private template trên Vast.ai

Vào `Templates -> My Templates -> Create New Template`:

| Trường | Giá trị |
|---|---|
| Name | `poc-local-ai-single-domain` |
| Image Path:Tag | Giá trị `${IMAGE_REF}:${IMAGE_TAG}` đã push |
| Launch mode | `SSH` |
| Direct SSH | Bật |
| Recommended disk | `100 GB` |
| Visibility | `Private` |
| On-start script | Để trống |

Để lấy chính xác tên image cần điền:

```bash
printf '%s\n' "${IMAGE_REF}:${IMAGE_TAG}"
```

Copy nguyên một dòng dưới đây vào `Docker options`:

```text
-p 1111:1111 -p 8080:8080 -e PORTAL_CONFIG='localhost:1111:11111:/:Instance Portal|localhost:8080:18000:/:Local AI API' -e LLM_MODEL=Qwen/Qwen3-VL-8B-Instruct -e LLM_REVISION=0c351dd01ed87e9c1b53cbc748cba10e6187ff3b -e LLM_GPU_MEMORY_UTILIZATION=0.72 -e LLM_MAX_MODEL_LEN=8192 -e LLM_MAX_NUM_SEQS=4 -e EMBEDDING_MODEL=BAAI/bge-m3 -e EMBEDDING_REVISION=5617a9f61b028005a4858fdac845db406aefb181 -e EMBEDDING_GPU_MEMORY_UTILIZATION=0.15 -e MODEL_STARTUP_TIMEOUT_SECONDS=1800
```

Không thêm GitHub token, Hugging Face token hoặc API token vào Docker options.
File [`deploy/vast/template.json.example`](deploy/vast/template.json.example)
chứa cùng cấu hình để tham khảo.

## Bước 6 — chọn và thuê GPU

Từ template vừa tạo, chọn `Search offers`. Lần thử đầu nên chọn:

- Một GPU có ít nhất `32 GB VRAM`.
- `Max CUDA >= 12.9` vì image hiện tại dùng CUDA 12.9.
- Host `Verified`, reliability ưu tiên trên `99%`.
- On-demand, disk ít nhất `100 GB`.
- Network download tốt để tải model lần đầu.
- Tổng giá GPU, disk và bandwidth nằm trong ngân sách.

Không thuê offer ghi `Max CUDA 12.8` với image hiện tại, kể cả đó là RTX 5090.
Driver của host đó chưa đáp ứng CUDA runtime 12.9 trong image.

Thuê instance và chờ trạng thái `Running`. Vast tự pull image và Supervisor tự
khởi động embedding, LLM và gateway; không cần chạy lệnh deploy khác.

## Bước 7 — SSH và đợi model sẵn sàng

Trên instance card bấm `SSH`, copy nguyên lệnh Vast cung cấp và chạy ở terminal
máy cá nhân. Sau khi vào terminal của Vast:

```bash
nvidia-smi
df -h /workspace
supervisorctl status
```

Ba process cần ở trạng thái `RUNNING`:

```text
local-ai-embedding
local-ai-llm
local-ai-gateway
```

Theo dõi log nếu model còn đang tải hoặc process restart:

```bash
tail -f /var/log/portal/local-ai-embedding.log
```

```bash
tail -f /var/log/portal/local-ai-llm.log
```

```bash
tail -f /var/log/portal/local-ai-gateway.log
```

Nhấn `Ctrl+C` để thoát chế độ xem log. Khi model đã load xong, kiểm tra nội bộ:

```bash
curl --fail http://127.0.0.1:8001/health
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:18000/readyz
```

`readyz` chỉ thành công khi cả LLM/Vision và embedding đều sẵn sàng.

## Bước 8 — lấy public URL và API token

Trên instance card, bấm `Open`. Trong Instance Portal mở `Local AI API` và copy
URL dạng:

```text
https://four-random-words.trycloudflare.com
```

Đây là một base URL dùng chung cho chat, Vision và embedding. URL Quick Tunnel
có thể thay đổi sau khi tạo lại instance.

Mở một terminal mới trên máy cá nhân, `cd` vào repository rồi khai báo thông tin
đúng như instance card và URL vừa lấy:

```bash
export VAST_INSTANCE_IP=YOUR_VAST_INSTANCE_IP
export VAST_SSH_PORT=YOUR_VAST_SSH_PORT
export VAST_BASE_URL=https://YOUR-AI-HOST.trycloudflare.com
```

Tải token về file cục bộ mà không in token lên terminal:

```bash
umask 077
mkdir -p secrets
ssh -p "${VAST_SSH_PORT}" "root@${VAST_INSTANCE_IP}" \
  'cat /run/local-ai/gateway-token' > secrets/vast-api-token
chmod 600 secrets/vast-api-token
```

Không mở, in, gửi hoặc commit file token. `secrets/` đã được Git bỏ qua.

## Bước 9 — smoke test từ Internet

Chạy trên máy cá nhân tại thư mục repository:

```bash
bash deploy/vast/smoke.sh \
  --base-url "${VAST_BASE_URL}" \
  --token-file secrets/vast-api-token
```

Kết quả mong đợi:

```text
auth: ok
ready: ok
chat: ok
vision: ok
embedding: ok
```

Nếu năm dòng trên đều `ok`, public API, xác thực, LLM, Vision và embedding đã
hoạt động.

## Bước 10 — benchmark trên GPU

Chạy các lệnh sau trong terminal SSH của Vast:

```bash
cd /opt/local-ai
mkdir -p /workspace/reports

.venv/bin/local-ai-lab bench chat \
  --base-url http://127.0.0.1:18000 \
  --workload benchmarks/workloads/text.jsonl \
  --credential-file /run/local-ai/gateway-token \
  --concurrency 1,2,4 \
  --requests-per-level 10 \
  --output /workspace/reports/text

.venv/bin/local-ai-lab bench chat \
  --base-url http://127.0.0.1:18000 \
  --workload benchmarks/workloads/vision.jsonl \
  --credential-file /run/local-ai/gateway-token \
  --concurrency 1,2 \
  --requests-per-level 5 \
  --output /workspace/reports/vision

.venv/bin/local-ai-lab bench embedding \
  --base-url http://127.0.0.1:18000 \
  --workload benchmarks/workloads/embedding.jsonl \
  --credential-file /run/local-ai/gateway-token \
  --concurrency 1,2,4 \
  --requests-per-level 20 \
  --output /workspace/reports/embedding
```

Mở terminal SSH khác để theo dõi GPU và process:

```bash
watch -n 1 nvidia-smi
```

```bash
watch -n 2 supervisorctl status
```

Report text/Vision gồm TTFT, E2E latency, tokens/second, error rate và số request
đồng thời. Report embedding gồm latency, throughput và error rate. GPU samples
ghi nhận VRAM, utilization, nhiệt độ và điện khi `nvidia-smi` hoạt động.

## Bước 11 — kiểm tra long context

### 11.1 Tạo workload trên máy cá nhân

Tài liệu tải về không được commit vào Git. Nếu chưa có `War and Peace`, tải bản
plain text từ Project Gutenberg:

```bash
mkdir -p benchmarks/sources benchmarks/generated

curl --fail --location --retry 3 \
  --output benchmarks/sources/war-and-peace.en.txt \
  https://www.gutenberg.org/cache/epub/2600/pg2600.txt
```

Sinh bốn workload độc lập. Mỗi file có ba bài test với thông tin nằm ở đầu,
giữa và cuối tài liệu:

```bash
for context_window in 8192 32768 65536 131072; do
  uv run local-ai-lab workload long-context \
    --source benchmarks/sources/war-and-peace.en.txt \
    --source-id war-and-peace-en \
    --output "benchmarks/generated/war-and-peace-${context_window}.jsonl" \
    --context-windows "${context_window}" \
    --positions start,middle,end \
    --reserve-tokens 1024
done
```

Generator dùng đúng tokenizer và revision của Qwen3-VL. Mỗi prompt giữ lại
1.024 token cho chat template và output. Có thể mở file JSONL để xem nội dung,
nhưng không commit vì file 128K khá lớn.

### 11.2 Chạy bài 8K trên instance đầu tiên

Template mặc định đang có `LLM_MAX_MODEL_LEN=8192`, vì vậy chỉ upload workload
8K ở lần chạy đầu. Thực hiện trên máy cá nhân:

```bash
ssh -p "${VAST_SSH_PORT}" "root@${VAST_INSTANCE_IP}" \
  'mkdir -p /workspace/workloads'

scp -P "${VAST_SSH_PORT}" \
  benchmarks/generated/war-and-peace-8192.jsonl \
  "root@${VAST_INSTANCE_IP}:/workspace/workloads/"
```

Sau đó chạy trong terminal SSH của Vast:

```bash
cd /opt/local-ai

.venv/bin/local-ai-lab bench chat \
  --base-url http://127.0.0.1:18000 \
  --workload /workspace/workloads/war-and-peace-8192.jsonl \
  --credential-file /run/local-ai/gateway-token \
  --concurrency 1 \
  --requests-per-level 3 \
  --timeout 600 \
  --output /workspace/reports/long-context-8192
```

Trong `summary.json` và `summary.md`, kiểm tra:

- `evaluation.pass_rate` phải là `1.0`/`100%`.
- `evaluation_by_case` phải có kết quả riêng cho `start`, `middle`, `end`.
- Không có request lỗi hoặc OOM.
- Ghi lại TTFT, E2E latency, tokens/second và peak VRAM.

### 11.3 Tăng lên 32K, 64K và 128K

Không gửi workload lớn hơn giới hạn server. Sau khi 8K đạt, sửa Vast template và
tạo instance mới cho từng mức:

| Mức thử | `LLM_MAX_MODEL_LEN` | `LLM_MAX_NUM_SEQS` | GPU khởi điểm |
|---:|---:|---:|---|
| 8K | `8192` | `4` | 32 GB |
| 32K | `32768` | `1` hoặc `2` | 32 GB, cần benchmark |
| 64K | `65536` | `1` | Nên từ 48 GB |
| 128K | `131072` | `1` | Nên từ 96 GB hoặc dùng quantization |

Với mỗi instance, upload đúng file tương ứng rồi thay tên workload/output trong
lệnh ở mục 11.2. Nếu model không khởi động hoặc OOM, ghi nhận đó là giới hạn của
cấu hình; không tăng đồng thời context và concurrency.

## Bước 12 — tải report về máy cá nhân

Chạy trên máy cá nhân tại thư mục repository:

```bash
mkdir -p reports

scp -P "${VAST_SSH_PORT}" -r \
  "root@${VAST_INSTANCE_IP}:/workspace/reports" \
  ./reports/vast-instance
```

Kiểm tra đã có các file `raw.jsonl`, `summary.json` và `summary.md` trong thư mục
report vừa tải.

## Bước 13 — ngừng phát sinh phí

Sau khi chắc chắn report đã tải về:

1. Mở instance trên Vast.ai.
2. Chọn `Destroy` nếu không cần giữ dữ liệu.
3. Xác nhận instance đã biến mất khỏi danh sách đang chạy.

`Stop` vẫn có thể tiếp tục tính phí storage. `Destroy` xóa dữ liệu trên instance;
chỉ thực hiện sau khi đã tải report cần giữ.

## Khi gặp lỗi

| Hiện tượng | Việc cần làm |
|---|---|
| Image pull error | Xác nhận đúng image/tag và GHCR package đã public |
| CUDA/driver error | Chọn offer có `Max CUDA >= 12.9` |
| Model tải lâu | Xem log, bandwidth và `df -h /workspace` |
| OOM | Giảm concurrency, `LLM_MAX_NUM_SEQS` và `LLM_MAX_MODEL_LEN` |
| Long-context `pass_rate` thấp | Xem `evaluation_by_case` để biết model quên đầu, giữa hay cuối |
| `401` | Tải lại đúng token và giữ file ở mode `0600` |
| `502` hoặc `503` | Kiểm tra `supervisorctl status`, log và đợi model ready |
| URL không còn chạy | Mở lại Instance Portal và lấy Quick Tunnel URL mới |
| Không SSH được | Dùng đúng IP/port Vast cung cấp và kiểm tra SSH public key |

Hướng dẫn xử lý chi tiết hơn nằm trong
[`docs/vast-ai-first-run.md`](docs/vast-ai-first-run.md).

## Giới hạn hiện tại

- CUDA inference, VRAM fit và hiệu năng thật phải được xác minh trên Linux/NVIDIA.
- Cấu hình mặc định chỉ mở context 8K; 32K/64K/128K là các thử nghiệm riêng.
- Quick Tunnel phù hợp PoC, không phải endpoint production có SLA.
- Vast.ai là máy thuê ngoài; không đưa tài liệu nội bộ nhạy cảm lên đó.
- Public GitHub/GHCR không được chứa `.env`, token, private key, model weights,
  dữ liệu nội bộ hoặc raw report nhạy cảm.
- Monitoring Prometheus/Grafana đầy đủ dành cho stack on-premise trong
  [`compose.yaml`](compose.yaml); PoC Vast dùng `nvidia-smi`, Supervisor và metric
  loopback để giảm số process trên GPU thuê.

## Tài liệu liên quan

- [`docs/vast-ai-first-run.md`](docs/vast-ai-first-run.md): giải thích chi tiết
  từng bước Vast.ai.
- [`docs/gpu-stack.md`](docs/gpu-stack.md): kiến trúc và vận hành GPU stack
  on-premise.
- [`deploy/vast/template.env.example`](deploy/vast/template.env.example): toàn bộ
  biến cấu hình model cho Vast.
- [`benchmarks/sources/manifest.yaml`](benchmarks/sources/manifest.yaml): URL,
  checksum và mục đích của từng tài liệu benchmark công khai.
