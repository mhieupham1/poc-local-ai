# Benchmark source documents

Thư mục này chứa tài liệu công khai dùng cho long-context, RAG và Vision/OCR.
Các file tài liệu thực tế được Git bỏ qua; `manifest.yaml` là hồ sơ nguồn, phiên
bản và checksum để một lần benchmark có thể được tái lập.

## Bộ tài liệu hiện tại

- `war-and-peace.en.txt`: văn bản tiếng Anh rất dài cho context 32K–256K.
- `truyen-kieu.vi.wiki.txt`: văn bản tiếng Việt thuộc phạm vi công cộng.
- `kokoro.ja.utf8.txt`: văn bản tiếng Nhật đã chuyển từ bản Shift-JIS gốc.
- `luat-dat-dai-2024.vi.html`: tài liệu tiếng Việt có cấu trúc điều/khoản.
- `nist-ai-rmf-playbook.en.pdf`: PDF 147 trang cho RAG và citation.
- `nasa-apollo-operations-handbook-emu-volume-1.en.pdf`: PDF kỹ thuật 112 trang
  cho Vision/OCR.

Hai file `.txt` sinh từ PDF chỉ phục vụ đối chiếu text extraction; PDF là nguồn
chính cho bài test Vision.

## Nguyên tắc sử dụng

- Không đưa tài liệu nội bộ hoặc dữ liệu cá nhân vào thư mục này.
- Kiểm tra `sha256` trong `manifest.yaml` trước khi so sánh hai lần benchmark.
- Ghi checksum tài liệu vào report cùng model revision và cấu hình context.
- Không commit các file tải về. Chỉ commit README, manifest và mã sinh workload.
- Ghi công và tuân thủ điều khoản của từng nguồn. Project Gutenberg chỉ tuyên
  bố bản tương ứng thuộc phạm vi công cộng tại Hoa Kỳ và yêu cầu người dùng ở
  nơi khác tự kiểm tra luật áp dụng.

