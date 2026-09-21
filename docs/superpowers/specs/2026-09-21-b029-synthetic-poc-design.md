# Thiết kế PoC B-029: đối chiếu báo cáo thành tích

## Mục tiêu

Chứng minh stack Local AI đã triển khai trên Vast có thể hỗ trợ nghiệp vụ
**B-029 — Xác nhận thành tích**: đọc một báo cáo sản xuất dạng ảnh hoặc PDF
scan, so sánh các trường đã trích xuất với một bản ghi mô phỏng Kintone, và
trả về các trường khớp/lệch để con người xác nhận.

PoC phải sử dụng đủ ba năng lực đang có:

1. Qwen3-VL-8B đọc báo cáo scan (Vision + LLM).
2. BGE-M3 xếp hạng các quy tắc đối chiếu có liên quan (Embedding).
3. Logic đối chiếu xác định kết quả một cách quyết định, không để LLM tự
   quyết định số liệu đúng/sai.

## Bối cảnh và quyết định

API inference hiện có là cổng công khai duy nhất, bảo vệ bằng Bearer token:

```text
https://<host>/v1/chat/completions  # LLM và Vision
https://<host>/v1/embeddings        # BGE-M3
```

**Quyết định:** B-029 là một CLI client gọi hai API trên, không phải service
mới hay endpoint public mới. Điều này giữ nguyên gateway, Docker image, Vast
template, xác thực và benchmark hiện hữu.

```text
PNG/JPEG hoặc PDF scan
        |
        |  POST /v1/chat/completions (ảnh dạng data:image)
        v
JSON trích xuất đã validate
        |
Kintone record mô phỏng ----> comparator quyết định ----> khớp / lệch
        |                              |
Quy tắc B-029 ----> POST /v1/embeddings --+--> quy tắc liên quan
                                                       |
                                                       v
                                          báo cáo JSON + Markdown
                                          để con người xác nhận
```

vLLM hỗ trợ chat-completions đa phương thức và URL ảnh base64; Qwen3-VL có
hướng dẫn chạy qua vLLM/OpenAI-compatible API. Dùng `response_format` JSON
mode để yêu cầu output có cấu trúc, nhưng vẫn validate lại output bằng
Pydantic. [vLLM multimodal](https://docs.vllm.ai/en/stable/examples/generate/multimodal/),
[vLLM structured output](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/),
[Qwen3-VL](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct)

## Phạm vi v1

### Luồng người dùng

```bash
local-ai-lab poc b029 fixtures --output samples/b029/generated

local-ai-lab poc b029 run \
  --case samples/b029/generated/case-01.json \
  --base-url https://<host> \
  --credential-file /duong-dan/gateway-token \
  --output reports/b029/case-01
```

`fixtures` tạo mười trường hợp **synthetic** có nhãn rõ ràng `DEMO DATA — NOT
PRODUCTION`: năm trường hợp khớp và năm trường hợp có đúng một hoặc nhiều sai
khác biệt (ngày, work order, mã hàng, sản lượng, lỗi). Mỗi trường hợp gồm:

- ảnh PNG form báo cáo sản xuất mô phỏng;
- `case-xx.json` chứa đường dẫn ảnh, bản ghi Kintone giả, quy tắc đối chiếu và
  expected result;
- không có tên người, khách hàng, dữ liệu sản xuất hay credential thật.

`run` chấp nhận một PNG/JPEG hoặc PDF scan một trang. Với PDF, client render
trang đầu thành PNG trong bộ nhớ; không upload file, không lưu ảnh đã render.

### Schema nghiệp vụ cố định cho dữ liệu mô phỏng

| Field | Ý nghĩa |
|---|---|
| `work_date` | Ngày sản xuất, ISO `YYYY-MM-DD` |
| `work_order` | Mã lệnh sản xuất |
| `process` | Công đoạn, ví dụ `PRESS` hoặc `WELD` |
| `item_code` | Mã hàng |
| `actual_quantity` | Số lượng thực tế, số nguyên không âm |
| `defect_quantity` | Số lượng lỗi, số nguyên không âm |

Vision prompt chỉ được yêu cầu điền sáu field này hoặc `null` khi không đọc
được. Bất kỳ field thiếu, sai định dạng, hoặc JSON không hợp lệ đều cho kết
quả `needs_human_review`; nó không được coi là `match`.

### Đối chiếu và embedding

Comparator chuẩn hóa khoảng trắng, viết hoa mã, ngày ISO và số nguyên trước
khi so sánh. Kết quả là một danh sách difference với `field`,
`report_value`, `kintone_value` và `reason`.

Danh sách quy tắc mô phỏng được embed cùng một query mô tả case. Client tính
cosine similarity, lấy ba quy tắc cao nhất và đưa chúng vào phần giải thích.
Embedding chỉ để truy xuất ngữ cảnh; kết quả `match`/`mismatch` luôn do
comparator quyết định.

### Output

Mỗi lần chạy sinh ba file trong thư mục `--output`:

- `result.json`: case ID, extracted record, differences, selected rules,
  trạng thái `match` / `mismatch` / `needs_human_review`, model IDs và request
  IDs.
- `result.md`: báo cáo người dùng có bảng đối chiếu và nhãn **human review
  required**.
- `evaluation.json`: so sánh status/differences với expected fixture để tính
  pass/fail cho synthetic demo.

Không ghi ảnh input, ảnh render PDF, Bearer token hay nội dung raw của response
LLM vào output mặc định.

## An toàn và giới hạn

- Token chỉ được đọc từ file `0600` qua cơ chế hiện có; không có token trong
  JSON, command line, report hay Git.
- Không gọi Kintone API, không ghi dữ liệu vào Kintone, STREAM, Topre hoặc
  Dennou Koujou.
- Client chỉ gửi data URL ảnh vào gateway hiện có; không dùng URL Internet hay
  đường dẫn `file://`.
- Dữ liệu thật sau này phải nằm ngoài Git/Docker image, đã ẩn danh và chỉ được
  dùng trên hạ tầng được phê duyệt. Cần có mapping từ form thật sang sáu field
  trước khi dùng kết quả cho nghiệp vụ.
- PoC không chứng minh độ chính xác với chữ viết tay, template thật nhiều
  trang, hoặc quy tắc sản xuất thật. Các nội dung đó chỉ được đánh giá khi có
  dữ liệu đã được phép sử dụng.

## Không làm trong v1

- Frontend, upload web hoặc HTML/CSS.
- Endpoint `/poc/...` công khai mới.
- Database/vector database hoặc RAG nhiều tài liệu.
- Kintone API, tự động import/in phiếu, hoặc tự động xử lý chênh lệch.
- PDF nhiều trang, OCR chữ viết tay hay training/fine-tuning.

## Tiêu chí hoàn thành

1. `docker build` và toàn bộ smoke/benchmark API hiện có không đổi hành vi.
2. Mười fixture synthetic tạo lại được, không chứa thông tin nhạy cảm.
3. `poc b029 run` gọi cả `/v1/chat/completions` và `/v1/embeddings` qua token,
   tạo ba output không chứa raw image/token.
4. Các fixture khớp/lệch đạt expected result qua comparator; thiếu/sai JSON
   luôn yêu cầu người kiểm tra.
5. Unit tests không cần GPU; integration run trên Vast ghi nhận request IDs,
   latency đầu cuối và kết quả từng case.
6. README/runbook giải thích rõ đây là synthetic technical demo, không phải
   chứng nhận độ chính xác nghiệp vụ.

## Chuyển sang dữ liệu thật

Khi nghiệp vụ cung cấp dữ liệu, thay các fixture bằng 10–30 cặp đã ẩn danh:

1. PDF/ảnh báo cáo ngày và export Kintone tương ứng.
2. Mapping form thật → sáu field PoC.
3. Ground truth do người nghiệp vụ xác nhận.
4. Đo field-level extraction accuracy, mismatch detection precision/recall,
   latency và VRAM riêng; không dùng kết quả synthetic để suy ra các số này.
