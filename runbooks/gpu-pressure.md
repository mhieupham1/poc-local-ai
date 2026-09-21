# GPU pressure

1. Dừng benchmark mới và giữ nguyên manifest/profile đang chạy.
2. Kiểm tra VRAM, nhiệt độ, power và queue trong dashboard.
3. Nếu OOM: giảm concurrency trước; không tự đổi model hoặc precision.
4. Nếu quá nhiệt: dừng inference và kiểm tra tản nhiệt/phần cứng.
