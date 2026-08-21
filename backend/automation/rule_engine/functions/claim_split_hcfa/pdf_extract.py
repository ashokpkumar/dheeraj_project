"""
Claim Split HCFA — PART 1 (cont'd): parsing the downloaded PDF.

Ports oReadPdf.txt. Where the VBA wrote each box straight into a MAIN/
ClaimInfo/ClaimServiceLInes worksheet cell, this returns plain dicts —
`extract_claim()` is the one entry point script.py calls; it returns
    {"demographics": {...}, "service_lines": [...]}
mirroring the original two-sheet split (ClaimInfo = one row per claim,
ClaimServiceLInes = one row per service line) as two Python structures
instead of two Excel tabs.

*** CLAIM_REPRICING_INFORMATION and the COB/adjustment-detail readers are
the least confident part of this file *** — the VBA computes several field
boxes with hand-tuned offsets (e.g. `CDbl(CordSet(1)) - 23.25`) calibrated
against a specific rendered report layout we can't see. They're ported
as literally as possible below, each flagged inline, and need checking
against a real repriced-claim PDF before being trusted.
"""

from __future__ import annotations

from .pdf_backend import ClaimPdfReader

# ---------------------------------------------------------------------------
# Small string helpers — mirror PoBoxAdr_Collections / Reformat_Address VBA
# ---------------------------------------------------------------------------

_PO_BOX_VARIANTS = [
    "POST OFFICE BOX", "P.O BOX", "P.O. BOX", "P. O. BOX", "P.O.BOX",
    "P  O  BOX", "P  O BOX", "P O BOX", "POBOX",
]


def po_box_normalize(addr: str) -> str:
    """Mirrors PoBoxAdr_Collections VBA — normalize any PO Box spelling to 'PO BOX '."""
    if not addr or not addr.strip():
        return addr
    upper = addr.upper()
    for variant in _PO_BOX_VARIANTS:
        idx = upper.find(variant)
        if idx != -1:
            return addr[:idx] + "PO BOX " + addr[idx + len(variant):].lstrip()
    return addr


def reformat_address(raw: str) -> dict:
    """
    Mirrors Reformat_Address VBA. Input is a pipe-delimited block scraped
    from Box 32 / Box 33 — either "Name|Addr1|City, ST Zip" (3 parts) or
    "Name|Addr1|Addr2|City, ST Zip" (4 parts). The VBA parses the last part
    with a chain of InStr/Mid calls that only works for a "City, ST ZIP"
    shape; this does the same thing with one regex instead of copying that
    exact string-splicing, which comes out equivalent for well-formed input.
    """
    parts = [p.strip() for p in (raw or "").split("|")]
    out = {"NAME": "", "ADDR1": "", "ADDR2": "", "CITY": "", "STATE": "", "ZIP": ""}
    if len(parts) not in (3, 4):
        return out

    out["NAME"] = parts[0]
    out["ADDR1"] = po_box_normalize(parts[1])
    if len(parts) == 4:
        out["ADDR2"] = po_box_normalize(parts[2])
    csz = parts[-1]

    import re
    m = re.match(r"^\s*([^,]+),\s*([A-Za-z]{2})\s+(.+?)\s*$", csz)
    if m:
        out["CITY"], out["STATE"], out["ZIP"] = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    else:
        out["CITY"] = csz
    return out


# ---------------------------------------------------------------------------
# CLAIM_DEMOGRAPHICS_INFORMATION — Box-by-box HCFA-1500 page-1 extraction
# ---------------------------------------------------------------------------

def extract_demographics(reader: ClaimPdfReader, pdf_path: str, ccn: str) -> dict:
    """Mirrors CLAIM_DEMOGRAPHICS_INFORMATION VBA (always page 1)."""
    rp = lambda l, b, r, t: reader.read_page(pdf_path, 1, l, b, r, t)  # noqa: E731
    norm = lambda s: " ".join((s or "").split()).upper()  # noqa: E731

    d: dict = {"CLAIM_NO": ccn}
    d["INSURED_ID"] = norm(rp(373, 672, 476, 683))                                    # Box1
    d["PATIENT_NAME"] = norm(rp(23, 648, 205, 662))                                    # Box2
    d["PATIENT_DOB"] = norm(rp(228, 648, 306, 657)).replace(" ", "/")                  # Box3
    d["PATIENT_SEX"] = "M" if norm(rp(316, 648, 326, 657)) else ("F" if norm(rp(352, 648, 362, 657)) else "")
    d["INSURED_NAME"] = norm(rp(374, 648, 546, 662))                                   # Box4
    d["PATIENT_ADDR"] = po_box_normalize(norm(rp(23, 624, 205, 639)))                  # Box5
    d["PATIENT_CITY"] = norm(rp(23, 600, 203, 616))
    d["PATIENT_STATE"] = norm(rp(203, 600, 228, 616))
    d["PATIENT_ZIP"] = norm(rp(23, 576, 117, 592))
    d["PATIENT_PHONE"] = norm(rp(117, 576, 205, 592))
    d["PATIENT_REL"] = (                                                               # Box6
        "SELF" if norm(rp(251, 624, 261, 637)) else
        "SPOUSE" if norm(rp(287, 624, 300, 637)) else
        "CHILD" if norm(rp(315, 624, 327, 637)) else
        "OTHER" if norm(rp(351, 624, 362, 637)) else ""
    )
    d["INSURED_ADDR"] = po_box_normalize(norm(rp(374, 624, 593, 639)))                 # Box7
    d["INSURED_CITY"] = norm(rp(374, 600, 544, 616))
    d["INSURED_STATE"] = norm(rp(544, 600, 593, 616))
    d["INSURED_ZIP"] = norm(rp(374, 576, 465, 592))
    d["INSURED_PHONE"] = norm(rp(465, 576, 593, 592))
    d["INSURED_POLICY_GRP"] = norm(rp(374, 552, 569, 567))                             # Box11
    d["INSURED_DOB"] = norm(rp(374, 530, 475, 541)).replace(" ", "/")
    d["INSURED_SEX"] = "M" if norm(rp(504, 530, 514, 541)) else ("F" if norm(rp(554, 530, 564, 541)) else "")
    d["REF_PROVIDER"] = norm(rp(23, 362, 215, 377))                                    # Box17
    d["BOX17A"] = norm(rp(246, 374, 386, 374))
    d["BOX17B"] = norm(rp(246, 374, 386, 374))  # same coordinates as Box17a in the VBA — see IO reference flag
    d["HOSP_DATE_FROM"] = norm(rp(402, 362, 477, 374)).replace(" ", "/")               # Box18
    d["HOSP_DATE_TO"] = norm(rp(503, 362, 593, 374)).replace(" ", "/")

    # Box 21 — Diagnosis A..L, 4 columns x 3 rows
    dx_boxes = {
        "DX_A": (37, 315, 88, 325), "DX_B": (130, 315, 179, 325), "DX_C": (222, 315, 269, 325), "DX_D": (317, 315, 368, 325),
        "DX_E": (37, 304, 88, 315), "DX_F": (130, 304, 179, 315), "DX_G": (222, 304, 269, 315), "DX_H": (317, 304, 368, 315),
        "DX_I": (37, 292, 88, 304), "DX_J": (130, 292, 179, 304), "DX_K": (222, 292, 269, 304), "DX_L": (317, 292, 368, 304),
    }
    for key, box in dx_boxes.items():
        d[key] = norm(rp(*box))

    d["FED_TAX_ID"] = norm(rp(23, 99, 117, 110))                                       # Box25
    d["PATIENT_ACCT_NO"] = norm(rp(178, 99, 286, 110))                                 # Box26
    d["BOX28_TOTAL_CHARGE"] = norm(rp(384, 99, 453, 110)).replace(" ", ".").replace(",", "")
    d["BOX31_SUPPLIER"] = norm(rp(23, 45, 177, 71))                                    # Box31

    service_fac_raw = norm(rp(177, 53, 373, 90))                                       # Box32
    d["SERVICE_FAC_RAW"] = service_fac_raw
    sf = reformat_address(service_fac_raw)
    d["SERVICE_FAC_NAME"] = sf["NAME"]
    d["SERVICE_FAC_ADDR1"] = sf["ADDR1"]
    d["SERVICE_FAC_ADDR2"] = sf["ADDR2"]
    d["SERVICE_FAC_CITY"] = sf["CITY"]
    d["SERVICE_FAC_STATE"] = sf["STATE"]
    d["SERVICE_FAC_ZIP"] = sf["ZIP"]
    d["SERVICE_FAC_NPI"] = _strip_labels(norm(rp(184, 35, 259, 52)), ("A.|NPI", "|", "A.", "NPI"))  # Box32a
    d["BOX32B"] = _strip_labels(norm(rp(258, 35, 372, 52)), ("B.",))

    billing_raw = norm(rp(373, 58, 592, 88))                                           # Box33
    d["BILLING_RAW"] = billing_raw
    bp = reformat_address(billing_raw)
    d["BILLING_NAME"] = bp["NAME"]
    d["BILLING_ADDR1"] = bp["ADDR1"]
    d["BILLING_ADDR2"] = bp["ADDR2"]
    d["BILLING_CITY"] = bp["CITY"]
    d["BILLING_STATE"] = bp["STATE"]
    d["BILLING_ZIP"] = bp["ZIP"]
    d["BILLING_NPI"] = _strip_labels(norm(rp(372, 35, 454, 52)), ("A.|NPI", "|", "A.", "NPI"))  # Box33a
    d["BOX33B"] = _strip_labels(norm(rp(454, 35, 592, 52)), ("B.",))

    d["RESUBMISSION_CODE"] = norm(rp(372, 314, 454, 325))                              # Box22
    amt_paid = norm(rp(454, 99, 521, 115)).replace("$", "").replace("|", "")           # Box29
    d["AMOUNT_PAID"] = f"${amt_paid}" if amt_paid else ""

    return d


def _strip_labels(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        text = text.replace(label, "")
    return text.strip()


# ---------------------------------------------------------------------------
# CLAIM_SERVICELINES_INFORMATION — Box 24 service-line grid
# ---------------------------------------------------------------------------

def extract_service_lines(reader: ClaimPdfReader, pdf_path: str, ccn: str) -> list[dict]:
    """
    Mirrors CLAIM_SERVICELINES_INFORMATION VBA. Scans every page for a
    "HEALTH INSURANCE CLAIM FORM" marker, then reads up to 6 service lines
    per matching page. Matches the VBA's own (unusual) stop condition: as
    soon as a line's "Date of Service From" box comes back empty, extraction
    stops for the WHOLE PDF, not just the current page — `GoTo JUSTEXIT`
    jumps clear of both loops in the original.
    """
    total_pages = reader.total_pages(pdf_path)
    norm = lambda s: " ".join((s or "").split()).upper()  # noqa: E731
    lines: list[dict] = []

    for page in range(1, total_pages + 1):
        if not reader.text_coordinates(pdf_path, "HEALTH INSURANCE CLAIM FORM", page):
            continue

        bottom, top = 243.0, 256.0
        for line_no in range(1, 7):
            dos_from = norm(reader.read_page(pdf_path, page, 23, bottom, 82, top))
            if not dos_from:
                return lines  # mirrors GoTo JUSTEXIT — stop entirely, not just this page

            ndc = norm(reader.read_page(pdf_path, page, 193, bottom + 10, 245, top + 10))
            if not ndc:
                ndc = norm(reader.read_page(pdf_path, page, 245, bottom + 10, 335, top + 10)).replace("NDC#", "")

            svl = {
                "CLAIM_NO": ccn,
                "LINE_NO": line_no,
                "DOS_FROM": dos_from.replace(" ", "/"),
                "DOS_TO": norm(reader.read_page(pdf_path, page, 82, bottom, 148, top)).replace(" ", "/"),
                "POS": norm(reader.read_page(pdf_path, page, 148, bottom, 171, top)),
                "EMG": norm(reader.read_page(pdf_path, page, 171, bottom, 193, top)),
                "CPT_HCPCS": norm(reader.read_page(pdf_path, page, 193, bottom, 245, top)),
                "MOD_A": norm(reader.read_page(pdf_path, page, 245, bottom, 269, top)),
                "MOD_B": norm(reader.read_page(pdf_path, page, 269, bottom, 292, top)),
                "MOD_C": norm(reader.read_page(pdf_path, page, 292, bottom, 312, top)),
                "MOD_D": norm(reader.read_page(pdf_path, page, 312, bottom, 335, top)),
                "DX_POINTER": norm(reader.read_page(pdf_path, page, 335, bottom, 372, top)),
                "CHARGES": norm(reader.read_page(pdf_path, page, 372, bottom, 436, top)).replace(" ", ".").replace(",", ""),
                "DAYS_UNITS": norm(reader.read_page(pdf_path, page, 436, bottom, 464, top)).replace(",", ""),
                "EPSDT_FAMILY_PLAN": norm(reader.read_page(pdf_path, page, 464, bottom, 481, top)),
                "ID_QUAL": norm(reader.read_page(pdf_path, page, 481, bottom, 500, top)).replace("NPI", ""),
                "RENDERING_PROVIDER_ID": norm(reader.read_page(pdf_path, page, 500, bottom, 592, top)),
                "NDC": ndc,
            }
            extract_medicare_cob_line(reader, pdf_path, svl, total_pages, line_no)
            lines.append(svl)

            bottom -= 25
            top -= 25

    return lines


def extract_medicare_cob_line(reader: ClaimPdfReader, pdf_path: str, svl: dict, total_pages: int, line_no: int) -> None:
    """
    Mirrors Medicare_Cob_Information VBA — mutates `svl` in place with the
    line's Medicare/Medicaid COB "APPVD"/"PAID" amounts, when the claim has
    a COB support-document page at all.
    *** Fragile: assumes exactly one match per TextCoordinates() call
    (no "|" splitting) same as the VBA does — validate against a real PDF.
    """
    for page in range(1, total_pages + 1):
        if not reader.text_coordinates(pdf_path, "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT", page):
            continue

        line_info = reader.text_coordinates(pdf_path, f"{line_no:06d}", page).split(",")
        appvd = reader.text_coordinates(pdf_path, "APPVD", page).split(",")
        paid = reader.text_coordinates(pdf_path, "PAID", page).split(",")
        if len(line_info) < 4 or len(appvd) < 3 or len(paid) < 3:
            return

        b = float(line_info[1])
        t = float(line_info[3].replace("|", ""))
        left = float(paid[0])
        right = float(appvd[2])
        appvd_info = reader.read_page(pdf_path, page, left - 15, b, right, t).strip()
        right = float(paid[2])
        paid_info = reader.read_page(pdf_path, page, left, b, right, t).strip()
        svl["MEDICARE_APPVD"] = appvd_info.replace("$", "")
        svl["MEDICARE_PAID"] = paid_info.replace("$", "")
        return


# ---------------------------------------------------------------------------
# CLAIM_REPRICING_INFORMATION — repricing figures + claim-level totals
# ---------------------------------------------------------------------------

def extract_repricing_info(reader: ClaimPdfReader, pdf_path: str, service_lines: list[dict]) -> dict:
    """
    Mirrors CLAIM_REPRICING_INFORMATION VBA. Mutates `service_lines` in
    place (adding REPRICE_* / ALLOWED_REPRICED / DISCOUNT_* / ICES_EDC_REMARK
    per line, matched by position — same as the VBA writing into SVL rows by
    index) and returns the claim-level totals/flags dict.

    Only ports the newer ("ADDED 2025.11.06") KeyPattern set (DATE FRM,
    DATE THR, CPT/HCPCS, CHARGES, Allowed/, Discount/) — the older
    lowercase set (Date Frm, HCPCS, /Repriced, /Ineligible) used for the
    legacy PDF-viewer path was NOT ported. If claims fetched via
    get_pdf_claim_legacy() come back with these fields blank, that's why —
    port the old KeyPattern branch here too.
    """
    total_pages = reader.total_pages(pdf_path)
    norm = lambda s: " ".join((s or "").split()).upper()  # noqa: E731
    totals = {
        "TOTAL_REPRICED": 0.0, "TOTAL_DISCOUNTS": 0.0, "REPRICED_IND": "",
        "HIC_MEM_NO": "", "REPRICED_BY": "", "CLAIM_NTE": "", "TIMELY_FILING": "",
        "METHOD_INFO": "",
    }

    cob_page = None
    for page in range(1, total_pages + 1):
        if reader.text_coordinates(pdf_path, "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT", page):
            cob_page = page
            break
    if cob_page is not None:
        top_tbl = reader.text_coordinates(pdf_path, "Claim Control Number", cob_page).split(",")
        bottom_tbl_raw = reader.text_coordinates(pdf_path, "LINE#", cob_page)
        if top_tbl and bottom_tbl_raw:
            bottom_tbl = bottom_tbl_raw.split("|")[0].split(",")
            try:
                n = round(float(top_tbl[3].replace("|", "")))
                stop_n = round(float(bottom_tbl[1]))
                while n >= stop_n:
                    row_text = reader.read_page(pdf_path, cob_page, 30, n - 13, 580, n).strip()
                    if not row_text:
                        break
                    if "MEDICARE ID" in row_text.upper():
                        totals["HIC_MEM_NO"] = row_text.replace("Medicare ID", "").strip()
                    n -= 13
            except (ValueError, IndexError):
                pass

    repricing_page = None
    for page in range(1, total_pages + 1):
        if reader.text_coordinates(pdf_path, "REPRICE INFO, RENDERING PHYSICIAN, & NOTES", page):
            repricing_page = page
            break

    if repricing_page is not None:
        totals["REPRICED_IND"] = _read_labeled_field(reader, pdf_path, repricing_page, "Re-Price Ind", "RE-PRICE IND")
        totals["TIMELY_FILING"] = _read_labeled_field(reader, pdf_path, repricing_page, "Timely Filing", "TIMELY FILING")
        totals["CLAIM_NTE"] = _read_labeled_field(reader, pdf_path, repricing_page, "Claim NTE", "CLAIM NTE")
        totals["REPRICED_BY"] = _read_labeled_field(reader, pdf_path, repricing_page, "Re-Priced By", "RE-PRICED BY")
        totals["METHOD_INFO"] = _read_labeled_field(reader, pdf_path, repricing_page, "Method", "METHOD")

        srw = 0
        key_patterns = ["DATE FRM", "DATE THR", "CPT/HCPCS", "CHARGES", "Units", "Allowed/", "Discount/", "iCES/EDC Remark Code"]
        for pattern in key_patterns:
            page = repricing_page
            rw = srw
            while page <= total_pages:
                coords = reader.text_coordinates(pdf_path, pattern, page)
                if coords:
                    for match in coords.split("|"):
                        parts = match.split(",")
                        if len(parts) < 4:
                            continue
                        l, b, r, t = (float(x) for x in parts)
                        b2, t2 = b - 23.25, t - 15.25
                        if rw >= len(service_lines):
                            rw += 1
                            continue
                        svl = service_lines[rw]
                        if pattern == "DATE FRM":
                            svl["REPRICE_DATE_FROM"] = norm(reader.read_page(pdf_path, page, l, b2, r, t2))
                        elif pattern == "DATE THR":
                            svl["REPRICE_DATE_TO"] = norm(reader.read_page(pdf_path, page, l, b2, r, t2))
                        elif pattern == "CPT/HCPCS":
                            svl["REPRICE_CPT_HCPCS"] = norm(reader.read_page(pdf_path, page, l, b2, r, t2))
                        elif pattern == "CHARGES":
                            svl["REPRICE_CHARGES"] = norm(reader.read_page(pdf_path, page, l, b2, r, t2)).replace("$", "").replace(",", "")
                        elif pattern == "Units":
                            svl["REPRICE_UNITS"] = norm(reader.read_page(pdf_path, page, l, b2, r, t2)).replace(",", "")
                        elif pattern == "Allowed/":
                            val = norm(reader.read_page(pdf_path, page, l, b2, r, t2)).replace("$", "")
                            val = val.replace("REPRICED|", "").replace("REPRICED", "")
                            svl["ALLOWED_REPRICED"] = val
                            try:
                                totals["TOTAL_REPRICED"] += float(val) if val else 0.0
                            except ValueError:
                                pass
                        elif pattern == "Discount/":
                            val = norm(reader.read_page(pdf_path, page, l, b2, r, t2)).replace("$", "")
                            val = val.replace("INELIGIBLE|", "").replace("INELIGIBLE", "")
                            svl["DISCOUNT_INELIGIBLE"] = val
                            svl["DISCOUNT_REASON_CODE"] = norm(reader.read_page(pdf_path, page, r, b2, r + 41, t2)).replace(",", "")
                            try:
                                totals["TOTAL_DISCOUNTS"] += float(val) if val else 0.0
                            except ValueError:
                                pass
                        elif pattern == "iCES/EDC Remark Code":
                            svl["ICES_EDC_REMARK"] = norm(reader.read_page(pdf_path, page, l, b2 - 20, r, t2 - 10))
                        rw += 1
                page += 1

    totals["TOTAL_REPRICED"] = round(totals["TOTAL_REPRICED"], 2)
    totals["TOTAL_DISCOUNTS"] = round(totals["TOTAL_DISCOUNTS"], 2)
    return totals


def _read_labeled_field(reader: ClaimPdfReader, pdf_path: str, page: int, label: str, strip_label: str) -> str:
    coords = reader.text_coordinates(pdf_path, label, page)
    if not coords:
        return ""
    first = coords.split("|")[0].split(",")
    if len(first) < 4:
        return ""
    l, b, _r, t = (float(x) for x in first)
    text = reader.read_page(pdf_path, page, l, b, 575, t)
    text = " ".join((text or "").split()).upper()
    return text.replace(strip_label, "").strip()


# ---------------------------------------------------------------------------
# Medicare_Medicaid_Cob_Information — claim-level COB figures
# ---------------------------------------------------------------------------

_COB_KEY_FIELDS = {
    "Deductible": "DEDUCTIBLE",
    "Coinsurance": "COINSURANCE",
    "Calculated Approved Amount": "CALC_APPROVED_AMT",
    "Paid": "COB_PAID",
    "Patient Responsibility": "PATIENT_RESPONSIBILITY",
    "Non-Covered": "NON_COVERED",
    "Contractual": "CONTRACTUAL",
    "Medicare ID": "MEDICARE_ID",
    "Other Insurance Type": "OTHER_INS_TYPE",
}


def extract_medicare_medicaid_cob(reader: ClaimPdfReader, pdf_path: str) -> dict:
    """Mirrors Medicare_Medicaid_Cob_Information VBA. Claim-level, not per-line."""
    total_pages = reader.total_pages(pdf_path)
    norm = lambda s: " ".join((s or "").split()).upper()  # noqa: E731
    out = {v: "" for v in _COB_KEY_FIELDS.values()}
    out["ADJUSTMENT_DETAIL"] = ""

    cob_page = None
    for page in range(1, total_pages + 1):
        if reader.text_coordinates(pdf_path, "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT", page):
            cob_page = page
            break
    if cob_page is None:
        return out

    for label, key in _COB_KEY_FIELDS.items():
        coords = reader.text_coordinates(pdf_path, label, cob_page)
        if not coords:
            continue
        first = coords.split("|")[0].split(",")
        if len(first) < 4:
            continue
        l, b, _r, t = (float(x) for x in first)
        val = norm(reader.read_page(pdf_path, cob_page, l, b, 432, t))
        val = val.replace(label.upper(), "").replace(" ", "")
        out[key] = val

    # Adjustment detail table ("SEQ) GRP CD, ADJ RSN: AMT") — best-effort;
    # the VBA's header/line-item disambiguation here is one of the more
    # fragile bits of the whole macro (see module docstring).
    marker = reader.text_coordinates(pdf_path, "SEQ) GRP CD, ADJ RSN: AMT", cob_page)
    pieces = marker.split("|") if marker else []
    adj_parts: list[str] = []
    for piece in pieces:
        parts = piece.split(",")
        if len(parts) < 4:
            continue
        b = round(float(parts[1]))
        t = round(float(parts[3]))
        right = round(float(parts[2]))
        header_text = reader.read_page(pdf_path, cob_page, 36, b, right, t)
        if "LINE#" in header_text.upper():
            bb, tt = float(b), float(t)
            for _ in range(22):
                bb -= 12.44
                tt -= 12.44
                val = reader.read_page(pdf_path, cob_page, float(parts[0]), bb, right, tt).replace(" ", "")
                if not val:
                    val = reader.read_page(pdf_path, cob_page, float(parts[0]) + 5, bb + 5, right, tt + 5).replace(" ", "")
                if val:
                    adj_parts.append(val)
        else:
            bb, tt = float(b), float(t)
            for i in range(1, 5):
                bb -= 9
                tt -= 8
                val = reader.read_page(pdf_path, cob_page, float(parts[0]), bb, right, tt).replace(" ", "")
                if val.startswith(f"{i})"):
                    adj_parts.append(val)
    out["ADJUSTMENT_DETAIL"] = " ".join(adj_parts).strip()
    return out


# ---------------------------------------------------------------------------
# Top-level entry point — script.py calls this once per claim
# ---------------------------------------------------------------------------

def resolve_dx_code(demographics: dict, dx_pointer: str) -> str:
    """
    Resolves a Box-24 diagnosis-pointer letter (e.g. "A", or "A,B" — only the
    first letter is used, mirroring the VBA's `LEFT(RC[-3],1)` reduction in
    POPULATE_MAIN_SHEET) against the claim's Box-21 Dx list. Used at CPS-keying
    time to fill the line's diagnosis field, same role as MAIN column AF.
    """
    letter = (dx_pointer or "").strip()[:1].upper()
    if not letter or not letter.isalpha():
        return ""
    return demographics.get(f"DX_{letter}", "")


def extract_claim(reader: ClaimPdfReader, pdf_path: str, ccn: str) -> dict:
    """
    Mirrors the sequence Main.txt's cmdRun_Click runs per claim during
    "02.GET EDI DETAILS": demographics, then service lines, then repricing
    (mutates the service lines further), then claim-level COB, then rolls
    up total charges the same way `INF.Range("BI" & x) = Format(TotalCharges, "0.00")`
    does in the VBA.
    """
    demographics = extract_demographics(reader, pdf_path, ccn)
    service_lines = extract_service_lines(reader, pdf_path, ccn)

    total_charges = 0.0
    for svl in service_lines:
        try:
            total_charges += float(svl.get("CHARGES") or 0)
        except ValueError:
            pass
    demographics["TOTAL_CHARGES"] = f"{total_charges:.2f}"

    totals = extract_repricing_info(reader, pdf_path, service_lines)
    demographics["TOTAL_REPRICED"] = f"{totals['TOTAL_REPRICED']:.2f}" if totals["TOTAL_REPRICED"] else "-"
    demographics["TOTAL_DISCOUNTS"] = f"{totals['TOTAL_DISCOUNTS']:.2f}" if totals["TOTAL_DISCOUNTS"] else "-"
    demographics["REPRICED_IND"] = totals["REPRICED_IND"]
    demographics["HIC_MEM_NO"] = totals["HIC_MEM_NO"]
    demographics["REPRICED_BY"] = totals["REPRICED_BY"]
    demographics["CLAIM_NTE"] = totals["CLAIM_NTE"]
    demographics["TIMELY_FILING"] = totals["TIMELY_FILING"]
    demographics["METHOD_INFO"] = totals["METHOD_INFO"]

    demographics.update(extract_medicare_medicaid_cob(reader, pdf_path))

    for svl in service_lines:
        svl["DX_CODE"] = resolve_dx_code(demographics, svl.get("DX_POINTER", ""))

    return {"demographics": demographics, "service_lines": service_lines}
