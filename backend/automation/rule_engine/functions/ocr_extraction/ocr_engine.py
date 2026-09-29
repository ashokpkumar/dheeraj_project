"""
OCR Extraction — EasyOCR wrapper.

EasyOCR's `Reader` is expensive to construct (loads detection + recognition
model weights, several hundred MB, from disk/network on first use) — built
once per process and reused as a module-level singleton, not once per box
or per request. `easyocr` itself is imported lazily inside `get_reader()`
so the rest of this package (renderer.py, storage.py, and the
`ocr_extract_by_template` registered function's mere presence/registration)
still works in an environment where `easyocr` hasn't been installed yet —
only actually running an OCR crop requires it.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

_reader = None


def get_reader():
    global _reader
    if _reader is None:
        import easyocr  # noqa: PLC0415 — deliberately deferred, see module docstring
        print("[ocr_engine] Loading EasyOCR model weights (first call only, may take a while)...")
        _reader = easyocr.Reader(["en"], gpu=False)
        print("[ocr_engine] EasyOCR reader ready.")
    return _reader


def ocr_crop(image: Image.Image, box: tuple[float, float, float, float]) -> str:
    """
    `box` is (x0, y0, x1, y1) in the SAME pixel space as `image` — top-left
    origin, matching both PIL's own convention and the browser canvas the
    annotation UI draws on. Nothing in this package ever converts to PDF
    points (pdfplumber's bottom-left-origin convention used elsewhere in
    this repo's own claim_split_hcfa/claims_split_ub text-extraction code)
    — this module stays entirely in rendered-image pixel space, since OCR
    operates on a raster crop, not on pdfplumber's text/word objects.
    """
    x0, y0, x1, y1 = box
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    x0 = max(0, int(x0))
    y0 = max(0, int(y0))
    x1 = min(image.width, int(round(x1)))
    y1 = min(image.height, int(round(y1)))
    if x1 <= x0 or y1 <= y0:
        return ""

    cropped = image.crop((x0, y0, x1, y1))
    reader = get_reader()
    result = reader.readtext(np.array(cropped.convert("RGB")), detail=0, paragraph=True)
    return " ".join(result).strip()
