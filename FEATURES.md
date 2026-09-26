# Đối chiếu yêu cầu — v0.2.1

Các mục có luồng xử lý trong code. Bảng dưới ghi rõ phạm vi thực hiện; không đồng nghĩa hỗ trợ hoàn hảo mọi file PDF.

| # | Yêu cầu | Đã bổ sung / cách dùng | Giới hạn thực tế |
|---|---|---|---|
| 1 | PDF ↔ Word/Excel/PowerPoint/ảnh | Thêm file Office/ảnh để nhập PDF; menu chuyển đổi để xuất DOCX/XLSX/PPTX; PNG/JPG theo trang | Office nhập cần LibreOffice. DOCX giữ bố cục gần đúng. XLSX trích bảng/dòng chữ, không khôi phục công thức. PPTX có chế độ chữ/ảnh sửa được hoặc ảnh toàn trang; đồ họa phức tạp chỉ giữ đầy đủ ở chế độ ảnh. |
| 2 | Xoay/lật, cắt, xóa trang | Preview từng trang; trái/phải, trên/dưới, crop %, xóa | Crop là vùng hiển thị, không xóa nội dung bảo mật. |
| 3 | Sửa ảnh | Chọn ảnh, thay/xóa, kéo di chuyển/đổi kích thước, cắt lề ảnh | Ảnh inline không có xref cần tải ảnh thay thế khi di chuyển. Đồ họa vector không phải ảnh raster. Vùng ảnh chồng nhau có thể bị ảnh hưởng khi xóa pixel. |
| 4 | OCR | Tesseract từng trang; lớp chữ có thể tìm kiếm, chọn sửa và xuất | Cần eng/vie; kết quả nhận diện cần kiểm tra. Sửa chữ OCR xóa pixel vùng chữ cũ và dùng nền trắng; nền có hoa văn không được phục hồi tự động. |
| 5 | Bảng | Tìm bảng, sửa ô, thêm/bớt hàng/cột cuối, dựng bảng mới, chia đều độ rộng cột | Hỗ trợ bảng thông thường. Ô gộp, đường chéo, bảng scan không được bảo toàn như bảng native. Không tự đẩy nội dung ở dưới; phải mở rộng vùng trong khoảng trống. |
| 6 | Tổ chức trang | Kéo thả thứ tự; đảo toàn bộ; xóa; chèn trang trắng hoặc file sau trang chọn; trích xuất | Thứ tự mới được dùng khi xuất/tách/gộp. |
| 7 | Header/Footer/số trang | Áp dụng hàng loạt khi xuất; tùy chọn xóa chữ ở lề trên/dưới 36 pt trước khi thêm | Nhận diện lề theo vị trí, không hiểu ngữ nghĩa mọi tài liệu. Tùy chọn xóa có thể xóa nội dung thật trong lề, cần kiểm tra. |
| 8 | Split/Merge | Thêm nhiều file để gộp; khoảng trang để tách ZIP; trích xuất ra một PDF | Chia theo khoảng trang nhập, chưa chia tự động theo chương/bookmark. |
| 9 | Form thông minh | Phát hiện dòng chấm/gạch dưới/ô chữ nhật trống; chọn ứng viên để tạo AcroForm Text; sửa trường Text có sẵn | Nhận diện heuristic; người dùng xác nhận từng vùng. Kiểu checkbox/radio hiện chỉ được giữ lại, chưa có trình sửa chuyên biệt. Hiển thị tiếng Việt trong form tùy font/trình đọc PDF. |
| 10 | Redaction | Chọn vùng → xóa text, pixel ảnh và path chạm vùng → bôi đen → dọn metadata, ghi PDF mới | Chỉ phạm vi đã chọn, không tự tìm mọi bản sao thông tin. Không dùng crop hay watermark thay cho redaction. |
| 11 | Watermark | Chèn chữ/logo dưới nội dung, opacity/góc; tự quét chữ nghiêng/nhạt/lặp và ảnh lặp; chỉ xóa các ứng viên được tick | Phát hiện có thể sai. Watermark hòa vào ảnh scan không tách riêng tự động được; ảnh nền đục có thể che watermark đặt bên dưới. |
| 12 | eSign / Digital Certificate | Tải/vẽ/lưu chữ ký ảnh, kéo vào vị trí; ký PDF xuất bằng P12/PFX có private key | Không có USB Token, ký từ xa hay timestamp/LTV. Chữ ký cũ không được bảo toàn sau chỉnh sửa; ký mới sau cùng. |
| 13 | Parse & Reconstruct / sửa chữ | JSON scan bbox, spans/font, ảnh, path, bảng, form, vùng lề; sửa block, thêm/xóa chữ; 3 họ font Unicode, đậm/nghiêng/màu; word-wrap có chặn tràn/chồng | Không phải bộ tái dựng hoàn chỉnh cho mọi PDF. Đoạn sửa dùng font thay thế; không giữ mọi định dạng hỗn hợp trong một block. Chữ nghiêng theo góc chưa sửa trực tiếp. Không cam kết bố cục 100%. |

## Kiểm thử đã thực hiện trong môi trường phát triển

- 13 bài unit/integration về thao tác trang và chỉnh nội dung đã qua.
- DOCX/XLSX/PPTX xuất rồi nhập lại qua LibreOffice: đọc được PDF kết quả.
- OCR tiếng Anh trên trang raster, sửa lại chữ và kiểm tra ảnh render: đã qua. Chưa có mẫu thực tế tiếng Việt của người dùng để đo độ chính xác OCR.
- P12 tự ký tạm thời: chữ ký kiểm tra `intact=True`, `valid=True`; không có private key thử nghiệm trong gói.
- Kiểm tra cú pháp JS/Python, HTTP API và luồng DOM qua jsdom: chọn chữ, preview, áp dụng, hoàn tác và chuyển đủ 10 tab công cụ. Việc tải Chromium trong môi trường kiểm thử bị lỗi, nên chưa xác nhận toàn bộ hành vi kéo thả/giao diện trên trình duyệt thực tế.

## Chưa đáp ứng trọn vẹn kỳ vọng ban đầu

“Sửa mọi PDF như Word” và “giữ thiết kế gần 100%” chưa thể xác nhận với kiến trúc/thư viện hiện tại. Muốn tiến tới mức này cần bộ mẫu PDF thực tế và thêm xử lý font subset, paragraph reflow, bảng gộp, vector, clipping và text xoay. Bản v0.2.1 bổ sung các nhóm công cụ có xử lý thật, nhưng vẫn là bản dùng thử một người, chưa phải sản phẩm production hoàn chỉnh.
