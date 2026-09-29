"""
OCR Extraction — PDF page rasterization.

Renders a PDF page to a PIL Image via pdfplumber's `page.to_image()`, which
is itself backed by `pypdfium2` (a pure pip-installable PDFium binding —
confirmed already present in this environment as a pdfplumber dependency,
no external system renderer like Ghostscript/ImageMagick/poppler needed).
Used both by the annotation UI (to display a page for drawing boxes on) and
by the OCR extraction step (cropping the same rendered image at the same
DPI a saved template's box coordinates were drawn against).

DPI is significant: annotation box coordinates are stored in PIXEL space
(top-left origin) at whatever DPI the page was rendered at when the box was
drawn — the SAME DPI must be used again at extraction time, or the stored
pixel coordinates land on the wrong part of the page. Templates persist
their own `dpi` for exactly this reason (see storage.py); always render
with `dpi=template["dpi"]` when replaying a saved template, not the
module-level default.
"""

from __future__ import annotations

import pdfplumber
from PIL import Image

DEFAULT_DPI = 200


def get_page_count(pdf_path: str) -> int:
    with pdfplumber.open(pdf_path) as pdf:
        return len(pdf.pages)


def render_page_to_image(pdf_path: str, page_number: int, dpi: int = DEFAULT_DPI) -> Image.Image:
    """1-based page_number. Returns a standalone PIL.Image.Image (copied out
    of pdfplumber's own page/PDF handles before they close)."""
    with pdfplumber.open(pdf_path) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise ValueError(f"page {page_number} out of range (PDF has {len(pdf.pages)} pages)")
        page = pdf.pages[page_number - 1]
        page_image = page.to_image(resolution=dpi)
        return page_image.original.copy()
