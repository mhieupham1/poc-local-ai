# B-029 synthetic test documents

Đây là bộ **input để chạy demo kỹ thuật B-029**, không phải tài liệu mô tả
PoC và cũng không phải dữ liệu sản xuất thật. Mọi tệp đều có nhãn `DEMO DATA
— NOT PRODUCTION`.

## Nội dung

- `reports/`: mười báo cáo ngày giả lập, mỗi case có một PNG scan-like và một
  PDF một trang. Dùng PNG để test Vision; dùng PDF để test bước render PDF
  trước Vision.
- `kintone-export.synthetic.csv`: mười bản ghi nguồn giả lập, một bản ghi cho
  mỗi case.
- `ground-truth.synthetic.csv`: kết quả kỳ vọng do fixture quy định.
- `rules.synthetic.json`: sáu quy tắc giả lập để test embedding/retrieval.
- `cases/`: manifest ghép report, bản ghi nguồn và outcome kỳ vọng.
- `SHA256SUMS`: hash kiểm tra toàn vẹn của bộ fixture.

`case-01` đến `case-05` phải cho kết quả `match`. `case-06` đến `case-10`
phải cho kết quả `mismatch`; các trường lệch được ghi trong ground truth và
case manifest.

## Cách tái tạo

Chạy tại gốc repository trên macOS có `rsvg-convert`:

```bash
python3 tools/generate_b029_synthetic_documents.py --output samples/b029
(cd samples/b029 && shasum -a 256 -c SHA256SUMS)
```

Generator từ chối ghi đè một thư mục không rỗng. Nếu cần tạo bộ tạm khác để
thử, đổi `--output` sang một đường dẫn mới. Không thay nội dung bộ này bằng dữ
liệu thật; dữ liệu thật phải đi qua quy trình trong
[phiếu xin dữ liệu B-029](../../docs/b029-data-request.md).
