"""
Claims Split UB — PDF reading backend.

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

This is the SAME generic reading engine as claim_split_hcfa/pdf_backend.py
(word-picking/line-grouping logic identical, byte-for-byte copy) — the DLL's
interface is claim-type-agnostic, so there's nothing HCFA-specific to strip
out. Kept as its own copy rather than a shared import, matching the
convention every function package under rule_engine/functions/ already
follows (utils.py, etc. are each package's own copy, not shared).

*** VALIDATE AGAINST A REAL SAMPLE UB-04 PDF BEFORE TRUSTING THIS ***
This is the single highest-risk file in the whole port, same as it was for
claim_split_hcfa (see that module's history in the project's macro-docs
memory for the coordinate-convention and line-join bugs found there):
  * Coordinate convention: every VBA call reads
    ReadPage(file, page, LEFT, BOTTOM, RIGHT, TOP) with BOTTOM < TOP, which
    matches standard PDF space (origin bottom-left, y grows upward).
    pdfplumber's boxes are top-down (origin top-left), so `read_page`
    converts using the page height — but the DPI/point scale the VBA
    coordinates were calibrated against is unknown, same caveat as HCFA.
  * `is_marker_box`'s <=15x15pt "any overlap" threshold below was
    calibrated against claim_split_hcfa's specific narrow-checkbox fields
    (Box3 Sex, Box6 Relationship, Box11 Sex on a HCFA-1500). claims_split_ub
    reads a UB-04 form instead — a genuinely different box layout (Box 11
    Patient Sex, Box 17 Stat, and several of the 2-digit admission/condition
    fields in oReadPdf.txt's CLAIM_DEMOGRAPHICS_INFORMATION are similarly
    narrow). This threshold has NOT been re-validated against a real UB-04
    PDF — if any of those narrow fields come back blank while their
    neighbors work, recheck this threshold and the checkbox-merge issue
    that motivated it (see the inline comment on `is_marker_box` below)
    before assuming it's a coordinate bug.
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
            # See claim_split_hcfa/pdf_backend.py's history: joining with ""
            # instead of " " here collapses multi-word markers ("42 REV.CD.",
            # "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT", ...) into one token
            # that a space-containing needle can never match.
            text = " ".join(w["text"] for w in line).strip()
            idx = text.lower().find(needle_lower)
            if idx == -1:
                continue
            # Bound the box to just the word(s) that make up the match, not
            # the whole line's min/max — see claim_split_hcfa/pdf_backend.py
            # for why (a table header row with several column labels on one
            # visual line would otherwise return a box spanning the entire
            # row for every single-label match on it).
            end = idx + len(needle)
            matched_words = []
            pos = 0
            for w in line:
                w_start, w_end = pos, pos + len(w["text"])
                if w_end > idx and w_start < end:
                    matched_words.append(w)
                pos = w_end + 1  # +1 for the joining " "
            if not matched_words:
                continue
            x0 = min(w["x0"] for w in matched_words)
            x1 = max(w["x1"] for w in matched_words)
            top = min(w["top"] for w in matched_words)
            bottom = max(w["bottom"] for w in matched_words)
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
        # Select by each word's CENTER point rather than pdfplumber's
        # crop()/within_bbox() — see claim_split_hcfa/pdf_backend.py's long
        # inline comment for the full history (within_bbox() drops a word
        # that's a hair outside a thin box entirely; crop() pulls in a
        # neighboring row's whole label the moment any pixel overlaps).
        # Below a size threshold, narrow marker/checkbox-style fields use
        # "any overlap" instead — see the module docstring above: this
        # threshold was tuned for HCFA-1500 boxes and is UNVERIFIED for
        # UB-04's box layout.
        is_marker_box = (x1 - x0) <= 15 and (bottom_pp - top_pp) <= 15

        picked = []
        for w in pg.extract_words(use_text_flow=False, keep_blank_chars=False):
            if is_marker_box:
                if w["x0"] < x1 and w["x1"] > x0 and w["top"] < bottom_pp and w["bottom"] > top_pp:
                    picked.append(w)
                continue
            x_mid = (w["x0"] + w["x1"]) / 2
            y_mid = (w["top"] + w["bottom"]) / 2
            if x0 <= x_mid <= x1 and top_pp <= y_mid <= bottom_pp:
                picked.append(w)
        picked.sort(key=lambda w: (round(w["top"]), w["x0"]))
        # Group into visual lines (same 2pt "top" tolerance as _lines()
        # below) and join lines with "|", words within a line with " " —
        # some UB-04 boxes (e.g. Box 1/Box 2 provider name/address blocks)
        # span multiple visual lines the same way HCFA's Box 32/33 do.
        lines: list[list[dict]] = []
        for w in picked:
            if lines and abs(lines[-1][-1]["top"] - w["top"]) <= 2:
                lines[-1].append(w)
            else:
                lines.append([w])
        return "|".join(" ".join(w["text"] for w in line) for line in lines).strip()


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
