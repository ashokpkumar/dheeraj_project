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
            idx = text.lower().find(needle_lower)
            if idx == -1:
                continue
            # Bound the box to just the word(s) that make up the match —
            # NOT min/max across every word on the line (that used to be
            # the whole box). A repricing-table header row puts several
            # column labels on one visual line ("DATE FRM DATE THR
            # CPT/HCPCS CHARGES UNITS ALLOWED/ DISCOUNT/ METHOD ..."), so
            # matching "DATE FRM" against the whole line's bbox returned a
            # box stretching to the last header on that line. Every
            # per-line read below "DATE FRM" then used that box's left/
            # right edges, scooping up the entire row's data (dates,
            # charges, allowed/discount, method, provider ID, ...) into
            # what was meant to be just the date.
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
        # Select by each word's CENTER point, not pdfplumber's crop()/
        # within_bbox(). within_bbox() used to be here and dropped any
        # word not *entirely* inside the box — several HCFA boxes (Box 3
        # DOB/Sex, Box 22 Resubmission Code, …) are only 9-11pt tall,
        # tight enough to the glyph height that a hair of rounding put a
        # word's bbox a fraction of a point outside the box, and the
        # whole word got silently discarded (PATIENT_DOB/PATIENT_SEX/
        # RESUBMISSION_CODE coming back empty even though the coordinates
        # matched the VBA exactly). Swapping to crop() fixed that, but
        # crop() keeps a whole word as soon as it *overlaps* the box by
        # any amount — on the last Box 24 service line, whose row sits
        # right against the Box 25-30 label row beneath it, that pulled
        # the neighboring labels ("FEDERAL TAX I.D. NUMBER", "TOTAL
        # CHARGE", …) into every column of that line, corrupting values
        # like CHARGES ("140.00" became "140.00 28. TOTAL CHARGE").
        # Center-point matching keeps both fixes: a thin box's word is
        # still included when only its edge pokes out by a hair (its
        # center stays put), while a neighboring row's word — whose
        # center sits a full line-height away — no longer counts as a
        # hair-of-overlap match.
        picked = []
        for w in pg.extract_words(use_text_flow=False, keep_blank_chars=False):
            x_mid = (w["x0"] + w["x1"]) / 2
            y_mid = (w["top"] + w["bottom"]) / 2
            if x0 <= x_mid <= x1 and top_pp <= y_mid <= bottom_pp:
                picked.append(w)
        picked.sort(key=lambda w: (round(w["top"]), w["x0"]))
        # Group into visual lines (same 2pt "top" tolerance as _lines()
        # below) and join lines with "|", words within a line with " ".
        # A box spanning multiple visual lines (Box 32/33's Name/Addr1/
        # [Addr2]/City,ST-Zip block) needs "|" between lines — that's what
        # reformat_address() in pdf_extract.py splits on (`raw.split("|")`,
        # needing exactly 3 or 4 parts), mirroring the real DLL's ReadPage
        # and the VBA's `Split(StrAdr, "|")`. This was fixed once already
        # (joining with "|"), but the fix was lost when read_page() was
        # rewritten around center-point word picking to fix an unrelated
        # overlap bug — that rewrite flattened everything back to a plain
        # " ".join across all picked words regardless of line, which is
        # why Box32/Box33 (SERVICE FACILITY NAME/ADDR*/CITY/STATE/ZIP,
        # BILLING PROVIDER NAME/ADDR*/CITY/STATE/ZIP) came back blank again
        # even though SERVICE_FAC_RAW/BILLING_RAW (the un-split box text)
        # had data.
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
