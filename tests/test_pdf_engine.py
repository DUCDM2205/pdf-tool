import io
import json
import unittest
import zipfile

import fitz
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from pdf_engine import InputError, build_pdf, images_zip, import_file, parse_ranges, preview_png, split_zip


def make_pdf():
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(300, 400))
    c.setFillColorRGB(1, 0, 0); c.rect(10, 350, 50, 40, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 1); c.rect(235, 10, 50, 40, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0); c.drawString(90, 200, "FIRST")
    c.showPage(); c.drawString(90, 200, "SECOND"); c.save()
    return stream.getvalue()


class PdfFlowTest(unittest.TestCase):
    def setUp(self):
        source, pages = import_file("sample.pdf", make_pdf())
        self.sources = {"sample": source}
        self.entries = [{"source": "sample", "index": p["index"], "ops": [], "crop": {}} for p in pages]

    def test_reorder_insert_delete_and_merge(self):
        plan = [self.entries[1], {"blank": True, "width": 300, "height": 400, "ops": [], "crop": {}}, self.entries[0]]
        result = PdfReader(io.BytesIO(build_pdf(plan, self.sources)))
        self.assertEqual(len(result.pages), 3)
        self.assertIn("SECOND", result.pages[0].extract_text())
        self.assertEqual(result.pages[1].extract_text(), "")
        self.assertIn("FIRST", result.pages[2].extract_text())

    def test_flip_rotate_preview_matches_export(self):
        plan = {**self.entries[0], "ops": ["horizontal", "right", "vertical"]}
        preview = Image.open(io.BytesIO(preview_png(plan, self.sources)))
        exported = build_pdf([plan], self.sources)
        with fitz.open(stream=exported, filetype="pdf") as document:
            pix = document[0].get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
        self.assertEqual(preview.size, (pix.width, pix.height))
        self.assertEqual(preview.tobytes(), pix.samples)

    def test_crop_is_visual_and_numbering_watermark_are_added(self):
        plan = [{**self.entries[0], "crop": {"left": 10, "top": 5, "right": 10, "bottom": 5}}]
        data = build_pdf(plan, self.sources, {"header": "Hệ thống Việt Mỹ", "footer": "Bản nội bộ", "numberPages": True,
                                              "watermark": {"text": "BẢN NHÁP", "opacity": .2, "angle": -30}})
        reader = PdfReader(io.BytesIO(data))
        self.assertAlmostEqual(float(reader.pages[0].cropbox.width), 240)
        self.assertIn("1 / 1", reader.pages[0].extract_text())
        self.assertIn("BẢN NHÁP", reader.pages[0].extract_text())
        with fitz.open(stream=data, filetype="pdf") as doc:
            self.assertGreater(len(doc[0].get_pixmap().samples), 10_000)

    def test_split_and_images(self):
        data = split_zip(self.entries, self.sources, "1, 2")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            self.assertEqual(len(PdfReader(io.BytesIO(archive.read(archive.namelist()[0]))).pages), 1)
        images = images_zip(self.entries, self.sources, "png")
        with zipfile.ZipFile(io.BytesIO(images)) as archive:
            self.assertEqual(len(archive.namelist()), 2)
            self.assertEqual(Image.open(io.BytesIO(archive.read(archive.namelist()[0]))).format, "PNG")

    def test_image_import_and_invalid_range(self):
        image = Image.new("RGB", (40, 30), "green")
        stream = io.BytesIO(); image.save(stream, "PNG")
        source, pages = import_file("photo.png", stream.getvalue())
        self.assertEqual(source.kind, "image")
        self.assertEqual(len(pages), 1)
        with self.assertRaises(InputError): parse_ranges("0-3", 2)
        with self.assertRaises(InputError): build_pdf([{**self.entries[0], "crop": {"left": 45}}], self.sources)


if __name__ == "__main__":
    unittest.main()
