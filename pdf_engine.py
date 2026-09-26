"""PDF operations for the local Friday PDF prototype.

The page plan is shared by previews and downloads, so both use the same PDF
operations. Each entry references one uploaded source and one original page.
"""
from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import fitz
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import NameObject, RectangleObject
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


MAX_FILE = 50 * 1024 * 1024
MAX_PAGES = 250
FONT_PATH = Path(__file__).with_name("fonts") / "DejaVuSans.ttf"
pdfmetrics.registerFont(TTFont("FridayUnicode", str(FONT_PATH)))


class InputError(ValueError):
    pass


@dataclass
class Source:
    name: str
    data: bytes
    kind: str

    def reader(self) -> PdfReader:
        return PdfReader(io.BytesIO(self.data), strict=False)


def import_file(name: str, data: bytes) -> tuple[Source, list[dict]]:
    if not data or len(data) > MAX_FILE:
        raise InputError("File trống hoặc vượt giới hạn 50 MB.")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise InputError("File không phải PDF hợp lệ.")
        kind = "pdf"
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with fitz.open(stream=data, filetype=suffix.lstrip(".")) as image_doc:
                data = image_doc.convert_to_pdf()
        except Exception as exc:
            raise InputError("Không đọc được ảnh này.") from exc
        kind = "image"
    else:
        raise InputError("Chọn PDF hoặc ảnh PNG/JPG/WebP.")
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise InputError("PDF có mật khẩu chưa được hỗ trợ ở bản này.")
        count = len(reader.pages)
        if not 1 <= count <= MAX_PAGES:
            raise InputError(f"Mỗi file cần có 1–{MAX_PAGES} trang.")
        pages = [
            {"index": i, "width": round(float(p.mediabox.width), 1),
             "height": round(float(p.mediabox.height), 1), "rotation": p.rotation}
            for i, p in enumerate(reader.pages)
        ]
    except InputError:
        raise
    except Exception as exc:
        raise InputError("Không thể đọc file PDF này.") from exc
    return Source(name, data, kind), pages


def _validated_crop(page, crop: dict | None):
    if not crop:
        return
    try:
        left, top, right, bottom = (float(crop.get(k, 0)) for k in ("left", "top", "right", "bottom"))
    except (TypeError, ValueError) as exc:
        raise InputError("Lề cắt phải là số.") from exc
    if min(left, top, right, bottom) < 0 or max(left, top, right, bottom) > 40:
        raise InputError("Mỗi lề cắt cần nằm trong khoảng 0–40%.")
    if left + right >= 90 or top + bottom >= 90:
        raise InputError("Vùng cắt quá nhỏ.")
    box = page.cropbox
    x0, y0, x1, y1 = map(float, (box.left, box.bottom, box.right, box.top))
    w, h = x1 - x0, y1 - y0
    page.cropbox.lower_left = (x0 + w * left / 100, y0 + h * bottom / 100)
    page.cropbox.upper_right = (x1 - w * right / 100, y1 - h * top / 100)


def apply_page_ops(page, entry: dict):
    """Apply operations in click order; flip axes follow the visible rotation."""
    _validated_crop(page, entry.get("crop"))
    for action in entry.get("ops", []):
        if action == "left":
            page.rotate(-90)
        elif action == "right":
            page.rotate(90)
        elif action in ("horizontal", "vertical"):
            odd = page.rotation % 180 != 0
            x_axis = (action == "horizontal") != odd
            box = page.mediabox
            if x_axis:
                transform = Transformation(ctm=(-1, 0, 0, 1, float(box.left + box.right), 0))
                page.add_transformation(transform)
            else:
                transform = Transformation(ctm=(1, 0, 0, -1, 0, float(box.bottom + box.top)))
                page.add_transformation(transform)
            for ref in page.get("/Annots", []):
                annot = ref.get_object()
                if "/Rect" in annot:
                    x0,y0,x1,y1 = map(float,annot["/Rect"])
                    a=transform.apply_on((x0,y0));b=transform.apply_on((x1,y1))
                    annot[NameObject("/Rect")]=RectangleObject((min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])))
        else:
            raise InputError("Thao tác xoay/lật không hợp lệ.")


def _source_page(entry: dict, sources: dict[str, Source], readers: dict[str, PdfReader]):
    if entry.get("blank"):
        try:
            width, height = float(entry["width"]), float(entry["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError("Kích thước trang trắng không hợp lệ.") from exc
        if not 100 <= width <= 2000 or not 100 <= height <= 2000:
            raise InputError("Trang trắng cần kích thước từ 100 đến 2000 pt.")
        return (width, height)
    sid = entry.get("source")
    if sid not in sources:
        raise InputError("Nguồn trang không còn tồn tại. Hãy tải file lại.")
    if sid not in readers:
        readers[sid] = sources[sid].reader()
        if readers[sid].get_fields():
            readers[sid].add_form_topname("source_" + str(sid)[:12])
    reader = readers[sid]
    try:
        index = int(entry["index"])
        if index < 0:
            raise IndexError
        return reader.pages[index]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise InputError("Số trang nguồn không hợp lệ.") from exc


def build_pdf(entries: list[dict], sources: dict[str, Source], decoration: dict | None = None) -> bytes:
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_PAGES:
        raise InputError(f"Cần chọn 1–{MAX_PAGES} trang để xuất.")
    readers: dict[str, PdfReader] = {}
    writer = PdfWriter()
    for entry in entries:
        source_page = _source_page(entry, sources, readers)
        if isinstance(source_page, tuple):
            page = writer.add_blank_page(width=source_page[0], height=source_page[1])
        else:
            writer.append(readers[entry["source"]], pages=[int(entry["index"])], import_outline=False)
            page = writer.pages[-1]
        apply_page_ops(page, entry)
    # append() imports the canonical AcroForm tree, including parent fields.
    if decoration and any((decoration.get("header"),decoration.get("footer"),decoration.get("numberPages"),decoration.get("replaceHeaders"),(decoration.get("watermark") or {}).get("text"),(decoration.get("watermark") or {}).get("logo"))):
        intermediate = io.BytesIO(); writer.write(intermediate)
        with fitz.open(stream=intermediate.getvalue(), filetype="pdf") as doc:
            for p in doc:
                p.remove_rotation()
                # Explicitly requested margin replacement: remove text only.
                if decoration.get("replaceHeaders"):
                    p.add_redact_annot(fitz.Rect(0, 0, p.rect.width, min(36, p.rect.height)), fill=False)
                    p.add_redact_annot(fitz.Rect(0, max(0,p.rect.height-36), p.rect.width, p.rect.height), fill=False)
                    p.apply_redactions(images=0, graphics=0)
            writer = PdfWriter()
            writer.clone_document_from_reader(PdfReader(io.BytesIO(doc.tobytes(garbage=4))))
    if decoration:
        decorate_pdf(writer, decoration)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _safe_text(value, limit=160):
    return str(value or "")[:limit]


def _logo_image(data_url):
    if not data_url:
        return None
    if not re.match(r"^data:image/(png|jpeg|webp);base64,", data_url):
        raise InputError("Logo cần là ảnh PNG, JPG hoặc WebP.")
    raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
    if len(raw) > 5 * 1024 * 1024:
        raise InputError("Logo cần nhỏ hơn 5 MB.")
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        converted = io.BytesIO()
        image.convert("RGBA").save(converted, format="PNG")
    converted.seek(0)
    return ImageReader(converted)


def decorate_pdf(writer: PdfWriter, options: dict):
    watermark = options.get("watermark") or {}
    text = _safe_text(watermark.get("text"))
    logo = _logo_image(watermark.get("logo"))
    try:
        opacity = min(.8, max(.05, float(watermark.get("opacity", .18))))
        angle = max(-90, min(90, float(watermark.get("angle", -30))))
    except (TypeError, ValueError) as exc:
        raise InputError("Độ mờ hoặc góc watermark không hợp lệ.") from exc
    header = _safe_text(options.get("header"))
    footer = _safe_text(options.get("footer"))
    number_pages = bool(options.get("numberPages"))
    for index, page in enumerate(writer.pages):
        # Preserve the original PDF objects; these additions are their own layers.
        width, height = float(page.cropbox.width), float(page.cropbox.height)
        origin_x, origin_y = float(page.cropbox.left), float(page.cropbox.bottom)
        if not any((text, logo, header, footer, number_pages)):
            continue
        if text or logo:
            stream = io.BytesIO()
            c = canvas.Canvas(stream, pagesize=(width, height))
            c.saveState()
            c.translate(width / 2, height / 2)
            c.rotate(angle)
            c.setFillAlpha(opacity)
            if logo:
                iw, ih = logo.getSize()
                factor = min(width * .5 / iw, height * .3 / ih)
                c.drawImage(logo, -iw * factor / 2, -ih * factor / 2, iw * factor, ih * factor, mask="auto")
            if text:
                c.setFont("FridayUnicode", min(42, max(18, width / max(3, len(text) * .53))))
                c.setFillColor(colors.grey)
                c.drawCentredString(0, 0, text)
            c.restoreState()
            c.save()
            page.merge_transformed_page(PdfReader(io.BytesIO(stream.getvalue())).pages[0], Transformation().translate(origin_x, origin_y), over=False)
        if header or footer or number_pages:
            stream = io.BytesIO()
            c = canvas.Canvas(stream, pagesize=(width, height))
            c.setFont("FridayUnicode", 9)
            c.setFillColor(colors.HexColor("#344256"))
            if header:
                c.drawString(24, height - 24, header)
            if footer:
                c.drawString(24, 19, footer)
            if number_pages:
                c.drawRightString(width - 24, 19, f"{index+1} / {len(writer.pages)}")
            c.save()
            page.merge_transformed_page(PdfReader(io.BytesIO(stream.getvalue())).pages[0], Transformation().translate(origin_x, origin_y), over=True)


def preview_png(entry: dict, sources: dict[str, Source]) -> bytes:
    data = build_pdf([entry], sources)
    with fitz.open(stream=data, filetype="pdf") as doc:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
        return pix.tobytes("png")


def split_zip(entries: list[dict], sources: dict[str, Source], ranges: str, decoration=None) -> bytes:
    groups = parse_ranges(ranges, len(entries))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for i, indices in enumerate(groups, 1):
            archive.writestr(f"phan_{i:02d}_trang_{indices[0]+1}-{indices[-1]+1}.pdf",
                             build_pdf([entries[k] for k in indices], sources, decoration))
    return stream.getvalue()


def parse_ranges(value: str, count: int) -> list[list[int]]:
    groups = []
    for chunk in str(value).split(","):
        match = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+)\s*)?", chunk)
        if not match:
            raise InputError("Nhập khoảng trang dạng 1-3, 4-6, 7.")
        a = int(match[1]); b = int(match[2] or a)
        if not 1 <= a <= b <= count:
            raise InputError(f"Khoảng trang phải nằm trong 1–{count}.")
        groups.append(list(range(a-1, b)))
    return groups


def images_zip(entries: list[dict], sources: dict[str, Source], image_type: str, decoration=None) -> bytes:
    if image_type not in {"png", "jpg"}:
        raise InputError("Định dạng ảnh không hợp lệ.")
    data = build_pdf(entries, sources, decoration)
    stream = io.BytesIO()
    with fitz.open(stream=data, filetype="pdf") as doc, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for i, page in enumerate(doc, 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            if image_type == "png":
                raw = pix.tobytes("png")
            else:
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                out = io.BytesIO(); image.save(out, "JPEG", quality=90)
                raw = out.getvalue()
            archive.writestr(f"trang_{i:03d}.{image_type}", raw)
    return stream.getvalue()
