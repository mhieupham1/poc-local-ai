# Service down

1. Kiểm tra `docker compose ps` và target `up` trong Prometheus.
2. Đọc log theo request ID; không in prompt hoặc Authorization.
3. Kiểm tra GPU OOM, disk và model revision trước khi restart đúng một service.
4. Chờ readiness và chạy smoke request trước khi mở lại lưu lượng.
