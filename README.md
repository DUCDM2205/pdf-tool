# Friday PDF Studio — Local v0.2.1

Web app Python + HTML/CSS/JS mở trong trình duyệt tại http://127.0.0.1:8765. Xử lý tài liệu ở máy bạn, dùng một người, chưa có tài khoản/Google login.

**Cách cài và chạy:** xem [INSTALL.md](INSTALL.md). **Đối chiếu đầy đủ yêu cầu:** xem [FEATURES.md](FEATURES.md).

## Bắt đầu

1. Thêm PDF/Office/ảnh. Nhiều file được gộp theo thứ tự hiển thị.
2. Chọn trang → **Sửa chữ, ảnh & ký tên**.
3. Chọn công cụ trên thanh ngang, bấm vào chữ/ảnh/bảng/form trên trang. Hoặc kéo vùng trống để tạo vùng mới.
4. Nhập nội dung hoặc tải ảnh, kéo khung để di chuyển, kéo góc để đổi kích thước. Bấm **Xem thử thay đổi → Áp dụng vào trang**.
5. Đóng màn hình sửa để xoay/lật/cắt trang, kéo thả sắp xếp, thêm trang, tách/trích xuất.
6. Đặt Header/Footer/số trang/watermark rồi **Xuất PDF**. Ký chứng thư là bước xuất cuối.

Có 25 bước hoàn tác nội dung cho mỗi trang trong phiên hiện tại. File gốc không bị ghi đè. Phải xuất tài liệu trước khi đóng app; dữ liệu làm việc nằm trong RAM. Chữ ký hình ảnh chỉ lưu trên trình duyệt khi bạn bấm Lưu và có nút Xóa.

## Kiến trúc

- `app.py`: HTTP API, nguồn tài liệu trong RAM, xử lý tuần tự thao tác MuPDF.
- `pdf_engine.py`: tổ chức trang, gộp/tách, xuất ảnh, trang trí hàng loạt; chung luồng cho preview và export.
- `editor_engine.py`: scan text/bbox/font/đồ họa/ảnh/bảng/form → JSON + preview → chỉnh vùng chọn trên bản sao → kiểm tra overflow/collision → xuất PDF mới.
- `converters.py`: pdf2docx, openpyxl, python-pptx, LibreOffice và pyHanko.
- `static/`: giao diện chọn đối tượng, kéo thả, preview, thao tác và hoàn tác.
- `fonts/`: font Unicode được nhúng cho chữ mới, kèm giấy phép.

Đây là kiến trúc **giữ các đối tượng gốc, tái tạo vùng sửa**. Không tái dựng toàn trang thành HTML rồi in lại: cách đó chưa đảm bảo giữ mọi clipping path, transparency, embedded font subset hoặc chữ ký cũ. JSON scan cung cấp tọa độ, thông tin font, spans, đường nét, vùng Header/Footer suy đoán. Font gốc được ghi nhận nhưng chữ thay thế dùng font Unicode người dùng chọn; không hứa giữ font gốc hoặc layout 100% trên mọi PDF.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Các bài kiểm tra bao gồm wrap tiếng Việt, chặn tràn/chồng chữ, giữ ảnh, xóa nội dung redaction, di chuyển ảnh, form canonical, bảng, chuyển Excel/PowerPoint và thao tác trang. Kiểm tra tích hợp thực hiện thêm Office hai chiều, OCR sửa lớp chữ và chữ ký P12 thử nghiệm. Chi tiết điều kiện và giới hạn xem FEATURES.md.

## Giới hạn tài liệu

50 MB/file, 250 trang/lần xuất. PDF có mật khẩu chưa hỗ trợ. Xoay/lật là thao tác từng trang. Cắt lề dùng CropBox: phần ngoài vùng nhìn vẫn có thể tồn tại, không thay thế Redaction.

Redaction loại text/ảnh/đồ họa trong vùng, dọn metadata và ghi mới với garbage collection; không chỉ vẽ hình đen. Nó chỉ xử lý vùng/trang được chọn; bản gốc và lịch sử hoàn tác vẫn còn trong phiên. Không cam kết chứng nhận bảo mật cho mọi cấu trúc PDF; kiểm tra bản xuất và các bản sao của cùng thông tin trên trang khác.

Font DejaVu kèm bản quyền tại `fonts/DejaVu-LICENSE.txt`. MuPDF/PyMuPDF và các thành phần khác có giấy phép riêng; kiểm tra giấy phép trước khi phân phối dịch vụ.

## Bản sửa v0.2.1

Sửa lỗi chặn chữ có sẵn trên ảnh nền. Khi chèn chữ mới lên ảnh, bật **Cho phép đặt chữ lên ảnh**. Kiểm tra tràn vùng và chồng lên chữ khác vẫn hoạt động. Người dùng v0.2 chỉ cần thay `editor_engine.py`, `static/app.js`, `static/index.html`, khởi động lại app và Ctrl+F5; không cần cài lại thư viện.
