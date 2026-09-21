# Local AI Lab Learning Log

Mỗi phase thêm một mục ngắn theo mẫu: **Learn → Observe → Interpret → Decide → Escalate**. Không dán prompt, credential hoặc dữ liệu nội bộ vào log.

## Phase 1 — Foundation

### Learn

- Control plane có thể phát triển/test độc lập GPU; inference performance thì không.
- “Config hợp lệ” gồm cả cấu trúc template và runtime credential tồn tại với permission đúng.

### Observe

- Máy phát triển: macOS, Python 3.12, không có NVIDIA GPU.
- Project sử dụng `uv`; GPU dependencies chưa được cài trên máy phát triển.
- Runtime config chỉ giữ đường dẫn credential `0600`, không đọc/nạp secret vào manifest.
- Manifest bắt buộc UTC, Git commit, workload SHA-256 và được ghi atomic.

### Interpret

- Máy hiện tại đủ để xây và kiểm tra control plane, schema, CLI cùng deployment dry-run.
- Không thể dùng kết quả trên Mac để kết luận CUDA compatibility, VRAM fit, TTFT hoặc tokens/second của GPU.

### Decide

- Giữ Python control plane độc lập GPU.
- Chỉ cài GPU runtime sau khi Phase 2 preflight đạt trên target Linux/NVIDIA.
- Không thuê Vast khi PoC charter còn `UNAPPROVED`.

### Escalate

- Nhờ security/IT nếu không xác định được data class hoặc inbound/egress policy.
- Nhờ infrastructure/vendor nếu driver, CUDA, PCIe topology, power hoặc cooling không khớp compatibility matrix.
- Dừng và escalation nếu gặp CUDA OOM lặp lại; không tự giảm model/context/precision ngoài fallback branch đã ghi manifest.
- Dừng benchmark nếu metric không có workload hash, model revision hoặc warm-up separation.
