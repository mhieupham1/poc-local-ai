# PoC Charter — Local AI Inference Lab

Status: **UNAPPROVED — không được thuê GPU hoặc dùng dữ liệu nội bộ**

## Outcome

Chứng minh một API AI nội bộ có thể chạy LLM/Vision, embedding và reranker; đo được hiệu năng/chất lượng; sau đó chuyển cùng client contract sang server GPU on-premise.

## Use case control

- Use case: hỏi đáp tài liệu nội bộ kiểu NotebookLM bằng tiếng Việt.
- Input đại diện: PDF có text, PDF scan, ảnh trang tài liệu và Markdown.
- Output: câu trả lời có citation; từ chối trả lời khi không có bằng chứng.
- Phạm vi PoC Vast.ai: chỉ tài liệu synthetic/public đã được kiểm tra thủ công.

Đây là workload control để xây lab, chưa phải phê duyệt đưa dữ liệu thật lên hệ thống.

## Acceptance gates

- API text streaming, Vision, embedding và reranking hoạt động qua private endpoint.
- Report có TTFT, E2E latency, decoding TPS, aggregate TPS, queue, error và VRAM theo concurrency 1/2/4/8.
- Structured output hợp lệ ít nhất 95% trên fixture; retrieval recall@5 ít nhất 90%; unsupported claim bằng 0 trên no-answer fixture.
- Model/embedding ports không public; credential, prompt và tài liệu không xuất hiện trong log/report mặc định.
- Cùng API contract và workload hash chạy lại được trên target on-premise.

Các ngưỡng trên chỉ là gate kỹ thuật ban đầu. Data owner phải duyệt bộ dữ liệu và ngưỡng nghiệp vụ trước pilot.

## Required approvals before Vast rental

| Decision | Current value | Required approver |
|---|---|---|
| Business/use-case owner | UNASSIGNED | Project sponsor |
| Data owner | UNASSIGNED | Business/data owner |
| Security owner | UNASSIGNED | Security/IT |
| Operations owner | UNASSIGNED | Infrastructure/IT |
| Allowed data class | `public`, `synthetic` only | Data + security owner |
| Maximum Vast spend | `USD 25` total; compute offer `<= USD 1/hour` | Budget owner |
| Maximum rental duration | `20 GPU-hours` | Budget owner |
| Pilot user/concurrency target | UNSET | Use-case owner |
| Monthly ingest/retention projection | UNSET | Data + operations owner |

## Mandatory stop conditions

- Phát hiện dữ liệu nội bộ/credential trong Vast workload, log hoặc report.
- Model port, metrics hoặc admin endpoint reachable trực tiếp từ Internet.
- Chi phí hoặc thời gian chạm giới hạn được duyệt.
- Preflight driver/CUDA/BF16/storage không đạt.
- Model license, revision, checksum hoặc image provenance chưa xác minh.
- Error rate, OOM, nhiệt độ hoặc VRAM vượt guard của experiment.

## Approval record

Charter chỉ chuyển sang `APPROVED` khi bảng Required approvals không còn `UNASSIGNED`/`UNSET` và có reference tới quyết định phê duyệt. Không ghi chữ ký, token hoặc thông tin bí mật vào file này.

Budget assumption được người yêu cầu chốt ngày 2026-09-14. Đây là trần chi phí, chưa thay thế phê duyệt owner/data/security/operations.
