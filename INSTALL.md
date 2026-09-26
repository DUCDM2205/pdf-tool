# Cài đặt và chạy lại

## Cập nhật từ bản v0.1

1. Xuất các tài liệu đang làm, rồi nhấn **Ctrl+C** trong Terminal.
2. Giải nén ZIP. Chép đè các file trong thư mục dự án cũ; giữ thư mục `.venv` của bạn.
3. Mở thư mục chứa `app.py` trong VS Code và chạy:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Mở http://127.0.0.1:8765 và nhấn **Ctrl+F5** để nạp giao diện mới.

## Cài mới

Dùng Python 3.11 hoặc 3.12. Trong Terminal của VS Code:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Không cần chạy Activate.ps1 hay đổi chính sách PowerShell.

## Những lần mở sau

```powershell
.\.venv\Scripts\python.exe app.py
```

Hoặc bấm đúp `START.bat`. Giữ cửa sổ Terminal mở trong khi dùng. Dừng bằng Ctrl+C.

## Office → PDF

Cài LibreOffice từ https://www.libreoffice.org/download/download-libreoffice/ vào vị trí mặc định. App tự tìm `soffice.exe`. Nếu cài nơi khác, đặt đường dẫn trong Terminal trước khi chạy:

```powershell
$env:FRIDAY_SOFFICE = 'D:\LibreOffice\program\soffice.exe'
.\.venv\Scripts\python.exe app.py
```

Nút **Thêm PDF / Office / ảnh** nhận DOC/DOCX, XLS/XLSX, PPT/PPTX. App chuyển thành PDF rồi đưa vào danh sách trang. Font thiếu trên máy có thể làm thay đổi bố cục.

## OCR

Cài Tesseract OCR và các language data `eng`, `vie`. Tài liệu nguồn: https://tesseract-ocr.github.io/tessdoc/Installation.html

App tìm Tesseract trong PATH hoặc `C:\Program Files\Tesseract-OCR\tesseract.exe`. Khởi động lại app sau khi cài. Trong màn hình sửa trang chọn **OCR → Tiếng Việt + Anh → Áp dụng**. Nếu chỉ có gói tiếng Anh, chọn Tiếng Anh.

OCR chạy từng trang, tối đa 120 giây/lần. Trang mờ, chữ viết tay và bảng phức tạp có thể nhận sai.

## Chứng thư số

Cài requirements.txt là đủ để có pyHanko. Chọn **Ký chứng thư P12 / PFX**, chọn file có private key và nhập mật khẩu. Chứng thư/mật khẩu không được ghi vào file dự án hoặc localStorage. Chữ ký được tạo ở bước xuất cuối cùng. Kiểm tra bằng trình đọc PDF tin cậy; chứng thư tự ký có thể báo không tin cậy dù chữ ký toàn vẹn.

## Lỗi thường gặp

- Cổng 8765 đang dùng: dừng phiên app cũ bằng Ctrl+C rồi chạy lại.
- Thiếu module: chạy lại lệnh pip bằng đúng `.venv\Scripts\python.exe`.
- Giao diện cũ: Ctrl+F5 và kiểm tra nhãn **LOCAL v0.2.1**.
- Chữ không vừa: tăng khung cao/rộng hoặc giảm font; app không lưu thay đổi bị tràn.
- File không còn trong app khi chạy lại: dữ liệu làm việc nằm trong RAM. Xuất PDF trước khi đóng.
