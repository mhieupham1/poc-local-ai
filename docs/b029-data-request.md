# B-029 — Phiếu xin dữ liệu để kiểm chứng PoC

## Mục đích xin dữ liệu

Sau khi demo bằng dữ liệu mô phỏng chạy ổn, cần bộ mẫu thật đã được phép dùng
để trả lời hai câu hỏi: Vision có đọc được biểu mẫu hiện tại không, và các
trường lệch mà PoC phát hiện có đúng với nhận định của nghiệp vụ không.

Đây là yêu cầu dữ liệu để kiểm chứng; không phải yêu cầu tích hợp hay quyền ghi
vào Kintone.

## Bộ tối thiểu cần cung cấp

Mỗi mẫu là một **cặp khớp định danh được** giữa báo cáo giấy và dữ liệu Kintone
cùng ngày/lệnh sản xuất. Xin tối thiểu 10 cặp, phù hợp hơn là 20–30 cặp nếu
nghiệp vụ cho phép. Bộ mẫu nên có cả trường hợp khớp và đã biết là có chênh
lệch.

| Thành phần | Dạng mong muốn | Nội dung tối thiểu |
|---|---|---|
| Báo cáo ngày | PDF scan hoặc ảnh PNG/JPEG, mỗi tệp một trang | Ép hoặc Hàn lắp ráp; phần thể hiện sáu trường cần đối chiếu |
| Export Kintone tương ứng | CSV/XLSX hoặc JSON export chỉ đọc | Một bản ghi tương ứng với mỗi báo cáo, kèm khóa giúp ghép cặp |
| Bảng ground truth | CSV/XLSX riêng, do người nghiệp vụ xác nhận | ID mẫu, trạng thái khớp/lệch, trường lệch và giá trị đúng nếu có |
| Hướng dẫn biểu mẫu | PDF/ảnh hoặc buổi giải thích ngắn | Vị trí, cách ghi và quy tắc nghiệp vụ của từng trường |

Sáu trường PoC cần mapping rõ ràng là: `work_date`, `work_order`, `process`,
`item_code`, `actual_quantity`, `defect_quantity`. Nếu biểu mẫu/Kintone dùng
tên khác, chỉ cần chỉ ra trường tương ứng trong bảng mapping; không cần thay
đổi hệ thống nguồn.

## Câu hỏi cần người nghiệp vụ trả lời

1. Báo cáo hiện có viết tay, in sẵn, hay kết hợp cả hai? Có bao nhiêu mẫu form
   đang được sử dụng?
2. Khi người kiểm tra thấy số liệu không khớp hiện nay, họ xác minh với ai và
   kết quả được ghi ở đâu?
3. Sáu trường trên có đủ cho quyết định ban đầu không? Trường nào là bắt buộc,
   trường nào được phép bỏ trống?
4. Mã hàng, lệnh sản xuất và tên công đoạn có quy ước viết tắt nào cần chuẩn
   hóa không?
5. Có trường hợp một báo cáo phải ghép với nhiều bản ghi Kintone không?

Câu trả lời cho các câu này là điều kiện để đánh giá dữ liệu thật, không cần
chờ có tích hợp Kintone mới trả lời được.

## Bảo vệ dữ liệu khi cung cấp

- Không đưa tên người, chữ ký, số điện thoại, khách hàng, giá bán, token,
  password hay URL private vào bộ mẫu. Che/ẩn danh trước khi bàn giao.
- Không commit tệp mẫu thật vào GitHub, Docker image, fixture synthetic hay
  report benchmark.
- Vast.ai hiện chỉ dùng dữ liệu public/synthetic cho tới khi data owner và
  security phê duyệt bằng văn bản. Nếu chưa có phê duyệt, kỹ thuật sẽ dùng
  fixture synthetic có nhãn `DEMO DATA — NOT PRODUCTION`.
- Chỉ gửi qua kênh nội bộ được người sở hữu dữ liệu chấp thuận; xác định thời
  hạn giữ/xóa tệp trước khi bàn giao.

## Cách đánh giá sau khi nhận

Người nghiệp vụ giữ vai trò xác định ground truth. Kỹ thuật chạy mỗi cặp qua
PoC và báo cáo riêng: tỉ lệ đọc đúng theo trường, tỉ lệ phát hiện lệch, các
trường chưa đọc được, thời gian xử lý và các trường hợp cần người kiểm tra.

Không dùng kết quả của mười mẫu synthetic để thay cho các số liệu này.
