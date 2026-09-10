"""
Claim Split HCFA — PDF reading backend.

The VBA macro reads claim PDFs through a proprietary COM component
(`PdfClaimImageDetails.dll`, `ReadClaimDetails` class, registered at runtime
by oRegistry.txt) exposing three calls used throughout oReadPdf.txt:

    .TotalPages(path)                        -> page count
    .TextCoordinates(path, "label text", pg)  -> "L,B,R,T[|L,B,R,T...]"
    .ReadPage(path, pg, L, B, R, T)           -> text inside that box

We don't have that DLL's source, so this module is a best-effort Python
re-implementation of the same three-call interface using `pdfplumber`, so
the rest of the port (pdf_extract.py) can stay a near line-for-line
translation of the VBA instead of being restructured around a different API.

*** VALIDATE AGAINST A REAL SAMPLE PDF BEFORE TRUSTING THIS ***
This is the single highest-risk file in the whole port:
  * Coordinate convention: every VBA call reads
    ReadPage(file, page, LEFT, BOTTOM, RIGHT, TOP) with BOTTOM < TOP, which
    matches standard PDF space (origin bottom-left, y grows upward).
    pdfplumber's boxes are top-down (origin top-left), so `read_page`
    converts using the page height — but the DPI/point scale the VBA
    coordinates were calibrated against (screen pixels? PDF points? a fixed
    report-rendering resolution?) is unknown. If extracted text comes back
    empty/misaligned on a real PDF, a uniform scale factor is almost
    certainly what's missing — add it in one place here, not in every call
    site in pdf_extract.py.
  * Match semantics: `text_coordinates` does a case-insensitive substring
    search line-by-line and returns one "L,B,R,T" tuple per matching line,
    joined with "|" — mirroring how the VBA does
    `Split(TextCoordinates(...), "|")` and indexes into the pieces. The
    original DLL's exact matching rules (word-boundary? multi-line labels?)
    are still unverified, but one concrete bug in that area was found and
    fixed 2026-09-09: the per-line text used to be built by joining
    pdfplumber's word tokens with `""`, collapsing e.g.
    "HEALTH INSURANCE CLAIM FORM" into "HEALTHINSURANCECLAIMFORM" — which
    a needle containing spaces can never match. That made virtually every
    `if not reader.text_coordinates(...)` guard in pdf_extract.py take the
    "not found" branch regardless of the PDF's actual content. Now joined
    with `" "` instead.
"""

from __future__ import annotations

import pdfplumber


class ClaimPdfReader:
    """Python stand-in for the VBA `iREADER` (PdfClaimImageDetails.ReadClaimDetails) object."""

    def __init__(self):
        self._cache: dict = {}

    def _pdf(self, path: str):
        pdf = self._cache.get(path)
        if pdf is None:
            pdf = pdfplumber.open(path)
            self._cache[path] = pdf
        return pdf

    def close(self, path: str | None = None):
        """Release the pdfplumber handle(s). Call once done with a PDF/run."""
        if path is not None:
            pdf = self._cache.pop(path, None)
            if pdf is not None:
                pdf.close()
            return
        for pdf in self._cache.values():
            pdf.close()
        self._cache.clear()

    # ------------------------------------------------------------------
    # .TotalPages(path)
    # ------------------------------------------------------------------
    def total_pages(self, path: str) -> int:
        return len(self._pdf(path).pages)

    # ------------------------------------------------------------------
    # .TextCoordinates(path, "label", page) -> "L,B,R,T|L,B,R,T|..."
    # ------------------------------------------------------------------
    def text_coordinates(self, path: str, needle: str, page: int) -> str:
        needle = (needle or "").strip()
        if not needle:
            return ""
        pdf = self._pdf(path)
        if page < 1 or page > len(pdf.pages):
            return ""
        pg = pdf.pages[page - 1]
        needle_lower = needle.lower()

        matches = []
        for line in _lines(pg):
            # NB: pdfplumber's extract_words() returns one dict per
            # already-space-separated word — joining with "" (as this used
            # to) collapses "HEALTH INSURANCE CLAIM FORM" into
            # "HEALTHINSURANCECLAIMFORM", which a space-containing needle
            # can never match. Every multi-word marker search in
            # pdf_extract.py goes through this function, so that one
            # missing separator was enough to make text_coordinates()
            # return "" for virtually every real label — the `if not
            # reader.text_coordinates(...)` guards all over pdf_extract.py
            # would then always take the "not found" branch.
            text = " ".join(w["text"] for w in line).strip()
            if needle_lower in text.lower():
                x0 = min(w["x0"] for w in line)
                x1 = max(w["x1"] for w in line)
                top = min(w["top"] for w in line)
                bottom = max(w["bottom"] for w in line)
                # pdfplumber top-down -> PDF bottom-up (L, B, R, T)
                b = pg.height - bottom
                t = pg.height - top
                matches.append(f"{x0:.2f},{b:.2f},{x1:.2f},{t:.2f}")
        return "|".join(matches)

    # ------------------------------------------------------------------
    # .ReadPage(path, page, L, B, R, T) -> text within that box
    # ------------------------------------------------------------------
    def read_page(self, path: str, page: int, left: float, bottom: float, right: float, top: float) -> str:
        pdf = self._pdf(path)
        if page < 1 or page > len(pdf.pages):
            return ""
        pg = pdf.pages[page - 1]
        x0, x1 = sorted((float(left), float(right)))
        # PDF bottom-up (bottom, top) -> pdfplumber top-down (top, bottom)
        top_pp = pg.height - float(top)
        bottom_pp = pg.height - float(bottom)
        top_pp, bottom_pp = sorted((top_pp, bottom_pp))
        x0 = max(x0, 0.0)
        x1 = min(x1, pg.width)
        top_pp = max(top_pp, 0.0)
        bottom_pp = min(bottom_pp, pg.height)
        if x0 >= x1 or top_pp >= bottom_pp:
            return ""
        try:
            cropped = pg.within_bbox((x0, top_pp, x1, bottom_pp))
        except ValueError:
            return ""
        # A box spanning multiple visual lines (e.g. Box 32/33's Name /
        # Address / City,ST Zip block) comes back from the real DLL's
        # ReadPage with "|" between lines, NOT a space — Reformat_Address
        # (oReadPdf.txt) expects exactly that: `Split(StrAdr, "|")` into
        # 3-4 parts. Joining with " " here instead (as this used to)
        # collapses those lines into one run-on string, so
        # reformat_address() in pdf_extract.py always saw a 1-part result
        # and fell straight through to its "not 3 or 4 parts" blank
        # default — which is why Box32/Box33 (service facility / billing
        # provider) came back completely empty.
        return (cropped.extract_text() or "").replace("\n", "|").strip()


def _lines(page) -> list[list[dict]]:
    """Group a pdfplumber page's words into visual lines (same 'top' band)."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][-1]["top"] - w["top"]) <= 2:
            lines[-1].append(w)
        else:
            lines.append([w])
    return lines
