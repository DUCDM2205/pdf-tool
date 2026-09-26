"""Friday PDF local web app. Run `python app.py` then open localhost:8765."""
from __future__ import annotations

import json
import threading
import uuid
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from editor_engine import scan, edit, watermark_candidates
from converters import capabilities, office_to_pdf, convert_pdf, sign_pdf
from pdf_engine import InputError, MAX_FILE, Source, build_pdf, images_zip, import_file, preview_png, split_zip


HOST = "127.0.0.1"  # Local only; no account or external upload.
PORT = 8765
STATIC = Path(__file__).with_name("static")
SOURCES: dict[str, Source] = {}
LOCK = threading.RLock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_binary(self, name, data, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{name}"' if name else "inline")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self, limit):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise InputError("Dung lượng gửi không hợp lệ.") from exc
        if size < 1 or size > limit:
            raise InputError("File hoặc yêu cầu quá lớn.")
        data = self.rfile.read(size)
        if len(data) != size:
            raise InputError("Dữ liệu tải lên chưa đầy đủ.")
        return data

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}:
            self.send_json(403, {"error":"Nguồn yêu cầu không được phép."})
            return
        # MuPDF operations are serialized: its document engine is not thread-safe.
        with LOCK:
            self.handle_post()

    def handle_post(self):
        try:
            if self.path == "/api/upload":
                name = unquote(self.headers.get("X-File-Name", ""))
                if not name or len(name) > 200:
                    raise InputError("Tên file không hợp lệ.")
                raw = self.read_body(MAX_FILE)
                if Path(name).suffix.lower() in {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"}:
                    raw = office_to_pdf(name, raw)
                    name = Path(name).stem + ".pdf"
                source, pages = import_file(name, raw)
                sid = uuid.uuid4().hex
                with LOCK:
                    SOURCES[sid] = source
                self.send_json(200, {"source": sid, "name": name, "kind": source.kind, "pages": pages})
                return
            if self.path not in {"/api/preview", "/api/export", "/api/split", "/api/images", "/api/scan", "/api/edit", "/api/edit-preview", "/api/watermarks", "/api/convert", "/api/sign"}:
                self.send_json(404, {"error": "Không tìm thấy chức năng."})
                return
            payload = json.loads(self.read_body(20 * 1024 * 1024))
            if self.path == "/api/scan":
                self.send_json(200, scan(payload["page"], SOURCES))
            elif self.path in {"/api/edit", "/api/edit-preview"}:
                data = edit(payload["page"], SOURCES, payload["operation"])
                if self.path == "/api/edit-preview":
                    import fitz
                    with fitz.open(stream=data, filetype="pdf") as doc:
                        self.send_binary(None, doc[0].get_pixmap(matrix=fitz.Matrix(1.4,1.4)).tobytes("png"), "image/png")
                else:
                    sid = uuid.uuid4().hex
                    source, pages = import_file("Edited.pdf", data)
                    with LOCK:
                        SOURCES[sid] = source
                    self.send_json(200, {"source":sid,"pages":pages})
            elif self.path == "/api/watermarks":
                self.send_json(200, {"pages":watermark_candidates(payload["pages"], SOURCES)})
            elif self.path == "/api/convert":
                data = convert_pdf(build_pdf(payload["pages"], SOURCES, payload.get("decoration")), payload["target"], payload.get("mode", "editable"))
                self.send_binary("Friday-PDF."+payload["target"],data,"application/octet-stream")
            elif self.path == "/api/sign":
                data = sign_pdf(build_pdf(payload["pages"], SOURCES, payload.get("decoration")),payload["certificate"],payload.get("password", ""))
                self.send_binary("Friday-PDF-signed.pdf",data,"application/pdf")
            elif self.path == "/api/preview":
                data = preview_png(payload["page"], SOURCES)
                self.send_binary(None, data, "image/png")
            elif self.path == "/api/export":
                data = build_pdf(payload["pages"], SOURCES, payload.get("decoration"))
                self.send_binary("Friday-PDF.pdf", data, "application/pdf")
            elif self.path == "/api/split":
                data = split_zip(payload["pages"], SOURCES, payload["ranges"], payload.get("decoration"))
                self.send_binary("Friday-PDF-split.zip", data, "application/zip")
            else:
                data = images_zip(payload["pages"], SOURCES, payload["type"], payload.get("decoration"))
                self.send_binary("Friday-PDF-images.zip", data, "application/zip")
        except (InputError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc) if not isinstance(exc, KeyError) else "Thiếu thông tin yêu cầu."})
        except Exception as exc:
            print("Lỗi xử lý:", type(exc).__name__)
            self.send_json(500, {"error": "Có lỗi khi xử lý PDF. Xem cửa sổ Terminal để biết chi tiết."})

    def do_GET(self):
        if self.path == "/api/capabilities":
            self.send_json(200, capabilities())
            return
        if self.path.startswith("/api/"):
            self.send_json(404, {"error": "Không tìm thấy chức năng."})
            return
        return super().do_GET()


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Friday PDF đang chạy tại http://{HOST}:{PORT}")
    print("Nhấn Ctrl+C trong Terminal để dừng.")
    threading.Timer(1, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng Friday PDF.")
        server.server_close()
