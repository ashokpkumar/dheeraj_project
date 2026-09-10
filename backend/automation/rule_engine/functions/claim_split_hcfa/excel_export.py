"""
Claim Split HCFA — Excel workbook export.

Writes the same three-sheet workbook the VBA macro produces on its own
MAIN / ClaimInfo / ClaimServiceLInes worksheets — this was the missing
piece: `script.py` was only ever writing two flat CSVs (one per DataFrame),
with no Main sheet at all, so nothing reproduced the joined, macro-shaped
view the user actually reviews claims in.

Column headers/order below are not guessed from the screenshot alone —
each one is traced back to the exact VBA `Range("<letter>" & rW) = ...`
assignment it came from:
  - ClaimInfo   <- CLAIM_DEMOGRAPHICS_INFORMATION + Reformat_Address
                   (oReadPdf.txt) + the CLAIM_REPRICING_INFORMATION /
                   Medicare_Medicaid_Cob_Information writes Main.txt makes
                   into INF.Range("BI".."CE" & x)
  - ClaimServiceLInes <- CLAIM_SERVICELINES_INFORMATION + Medicare_Cob_Information
                   (oReadPdf.txt, columns A..AB) + the per-line reprice
                   writes CLAIM_REPRICING_INFORMATION makes into SVL columns
                   Q..Y
  - Main        <- POPULATE_MAIN_SHEET (oShared.txt), which is a join: one
                   Main row per ClaimServiceLInes row, decorated with a
                   handful of claim-level ClaimInfo/totals columns. That
                   join is recomputed here directly in Python (values, not
                   formulas) rather than written as literal Excel formulas.

Two things POPULATE_MAIN_SHEET does that this does NOT reproduce, on
purpose:
  - MAIN column W ("TOS") is never populated by POPULATE_MAIN_SHEET in the
    VBA either — it's a column the user fills in by hand before running
    "03.SPLIT CLAIM" (see oScratch.txt/oNonScratch.txt keying it as
    "TOS"). Left blank here for the same reason, not a bug.
  - MAIN columns M:R (NEW_CERT/NEW_CCN/NEW_DOS/NEWBORN_TYPE/NON_NEWBORN_SEQ,
    hidden in the original) are SCRATCH-mode *inputs* the user supplies
    before splitting, not something GET EDI DETAILS produces — they aren't
    part of this export either.

ClaimInfo also carries one faithfully-reproduced legacy bug: BOX17A and
BOX17B are read from identical PDF coordinates in the original VBA
(oReadPdf.txt lines 346-347), so they always come out equal here too —
that's the source workbook's own bug, not a porting mistake.
"""

from __future__ import annotations

from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

_THIN = Side(style="thin", color="B0B0B0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_GROUP_FILL = PatternFill("solid", fgColor="1F3864")     # box-group header row
_LABEL_FILL = PatternFill("solid", fgColor="BF9000")     # field-label header row
_REPRICE_FILL = PatternFill("solid", fgColor="2E75B6")   # "REPRICE INFO..." group
_COB_FILL = PatternFill("solid", fgColor="548235")       # "MEDICARE/MEDICAID/COB..." group
_MAIN_LEFT_FILL = PatternFill("solid", fgColor="000000")     # Main sheet, claim-level block
_MAIN_RIGHT_FILL = PatternFill("solid", fgColor="833C0B")    # Main sheet, per-line block

_GROUP_FONT = Font(color="FFFFFF", bold=True, size=8)
_LABEL_FONT = Font(color="FFFFFF", bold=True, size=8)
_DATA_FONT = Font(size=8)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autosize(ws, ncols: int, min_width: float = 9, max_width: float = 32) -> None:
    for col_idx in range(1, ncols + 1):
        letter = get_column_letter(col_idx)
        longest = 0
        for cell in ws[letter]:
            if cell.value is not None:
                longest = max(longest, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max_width, max(min_width, longest + 2))


# ---------------------------------------------------------------------------
# ClaimInfo — one row per claim
# ---------------------------------------------------------------------------

# (box group or None, column label, source key in the claim dict)
CLAIMINFO_COLUMNS: list[tuple[str | None, str, str]] = [
    (None, "CLAIM CONTROL NUMBER", "CLAIM_NO"),
    (None, "MACRO STATUS", "MACRO_STATUS"),
    ("BOX1A", "INSURED I.D. NUMBER", "INSURED_ID"),
    ("BOX2", "PATIENT'S NAME", "PATIENT_NAME"),
    ("BOX3", "PATIENT'S BIRTHDATE", "PATIENT_DOB"),
    ("BOX3", "PATIENT'S SEX", "PATIENT_SEX"),
    ("BOX4", "INSURED'S NAME", "INSURED_NAME"),
    ("BOX5", "PATIENT'S ADDRESS", "PATIENT_ADDR"),
    ("BOX5", "PATIENT'S CITY", "PATIENT_CITY"),
    ("BOX5", "PATIENT'S STATE", "PATIENT_STATE"),
    ("BOX5", "PATIENT'S ZIPCODE", "PATIENT_ZIP"),
    ("BOX5", "PATIENT'S TELEPHONE", "PATIENT_PHONE"),
    ("BOX6", "PATIENT REL TO INSURED", "PATIENT_REL"),
    ("BOX7", "INSURED'S ADDRESS", "INSURED_ADDR"),
    ("BOX7", "INSURED'S CITY", "INSURED_CITY"),
    ("BOX7", "INSURED'S STATE", "INSURED_STATE"),
    ("BOX7", "INSURED'S ZIPCODE", "INSURED_ZIP"),
    ("BOX7", "INSURED'S TELEPHONE", "INSURED_PHONE"),
    ("BOX11", "INSURED'S POLICY GRP", "INSURED_POLICY_GRP"),
    ("BOX11", "INSURED'S BIRTHDATE", "INSURED_DOB"),
    ("BOX11", "INSURED'S SEX", "INSURED_SEX"),
    ("BOX17", "NAME OF REFERRING PROVIDER", "REF_PROVIDER"),
    ("BOX17", "17A", "BOX17A"),
    ("BOX17", "17B. NPI", "BOX17B"),
    ("BOX18", "HOSPITALIZATION DATE FROM", "HOSP_DATE_FROM"),
    ("BOX18", "HOSPITALIZATION DATE TO", "HOSP_DATE_TO"),
    ("BOX21", "A", "DX_A"), ("BOX21", "B", "DX_B"), ("BOX21", "C", "DX_C"), ("BOX21", "D", "DX_D"),
    ("BOX21", "E", "DX_E"), ("BOX21", "F", "DX_F"), ("BOX21", "G", "DX_G"), ("BOX21", "H", "DX_H"),
    ("BOX21", "I", "DX_I"), ("BOX21", "J", "DX_J"), ("BOX21", "K", "DX_K"), ("BOX21", "L", "DX_L"),
    ("BOX25", "FEDERAL TAX I.D. NUMBER", "FED_TAX_ID"),
    ("BOX26", "PATIENT'S ACCOUNT NO.", "PATIENT_ACCT_NO"),
    ("BOX28", "TOTAL CHARGE (AS BILLED)", "BOX28_TOTAL_CHARGE"),
    ("BOX31", "SUPPLIER", "BOX31_SUPPLIER"),
    ("BOX32", "SERVICE FACILITY NAME", "SERVICE_FAC_NAME"),
    ("BOX32", "SERVICE FACILITY ADDR 1", "SERVICE_FAC_ADDR1"),
    ("BOX32", "SERVICE FACILITY ADDR 2", "SERVICE_FAC_ADDR2"),
    ("BOX32", "SERVICE FACILITY CITY", "SERVICE_FAC_CITY"),
    ("BOX32", "SERVICE FACILITY STATE", "SERVICE_FAC_STATE"),
    ("BOX32", "SERVICE FACILITY ZIP", "SERVICE_FAC_ZIP"),
    ("BOX32A", "SERVICE FACILITY NPI", "SERVICE_FAC_NPI"),
    ("BOX32B", "BOX32B", "BOX32B"),
    ("BOX33", "BILLING PROVIDER NAME", "BILLING_NAME"),
    ("BOX33", "BILLING PROVIDER ADDR 1", "BILLING_ADDR1"),
    ("BOX33", "BILLING PROVIDER ADDR 2", "BILLING_ADDR2"),
    ("BOX33", "BILLING PROVIDER CITY", "BILLING_CITY"),
    ("BOX33", "BILLING PROVIDER STATE", "BILLING_STATE"),
    ("BOX33", "BILLING PROVIDER ZIP", "BILLING_ZIP"),
    ("BOX33A", "BILLING PROVIDER NPI", "BILLING_NPI"),
    ("BOX33B", "BOX33B", "BOX33B"),
    ("BOX22", "RESUBMISSION CODE", "RESUBMISSION_CODE"),
    ("BOX29", "AMOUNT PAID", "AMOUNT_PAID"),
    (None, "TOTAL CHARGES", "TOTAL_CHARGES"),
    (None, "TOTAL REPRICED", "TOTAL_REPRICED"),
    (None, "TOTAL DISCOUNTS", "TOTAL_DISCOUNTS"),
    (None, "REPRICED IND", "REPRICED_IND"),
    (None, "HIC/MEMBER NO", "HIC_MEM_NO"),
    (None, "REPRICED BY", "REPRICED_BY"),
    (None, "CLAIM NOTE", "CLAIM_NTE"),
    (None, "TIMELY FILING", "TIMELY_FILING"),
    (None, "METHOD", "METHOD_INFO"),
    ("COB", "DEDUCTIBLE", "DEDUCTIBLE"),
    ("COB", "COINSURANCE", "COINSURANCE"),
    ("COB", "CALC APPROVED AMT", "CALC_APPROVED_AMT"),
    ("COB", "PAID", "COB_PAID"),
    ("COB", "PATIENT RESPONSIBILITY", "PATIENT_RESPONSIBILITY"),
    ("COB", "NON-COVERED", "NON_COVERED"),
    ("COB", "CONTRACTUAL", "CONTRACTUAL"),
    ("COB", "MEDICARE ID", "MEDICARE_ID"),
    ("COB", "OTHER INSURANCE TYPE", "OTHER_INS_TYPE"),
    ("COB", "ADJUSTMENT DETAIL", "ADJUSTMENT_DETAIL"),
]


# ---------------------------------------------------------------------------
# ClaimServiceLInes — one row per service line
# ---------------------------------------------------------------------------

CLAIMSVL_COLUMNS: list[tuple[str | None, str, str]] = [
    (None, "CLAIM CONTROL NUMBER", "CLAIM_NO"),
    ("BOX24A", "DATE OF SERVICE FROM", "DOS_FROM"),
    ("BOX24A", "DATE OF SERVICE TO", "DOS_TO"),
    ("BOX24B", "PLACE OF SERVICE", "POS"),
    ("BOX24C", "EMG", "EMG"),
    ("BOX24D", "CPT/HCPCS", "CPT_HCPCS"),
    ("BOX24D", "MOD 01", "MOD_A"),
    ("BOX24D", "MOD 02", "MOD_B"),
    ("BOX24D", "MOD 03", "MOD_C"),
    ("BOX24D", "MOD 04", "MOD_D"),
    ("BOX24E", "DIAGNOSIS POINTER", "DX_POINTER"),
    ("BOX24F", "CHARGES", "CHARGES"),
    ("BOX24G", "DAYS OR UNITS", "DAYS_UNITS"),
    ("BOX24H", "EPSDT FAMILY PLAN", "EPSDT_FAMILY_PLAN"),
    ("BOX24I", "I.D. QUAL", "ID_QUAL"),
    ("BOX24J", "RENDERING PROVIDER I.D. #", "RENDERING_PROVIDER_ID"),
    ("REPRICE", "DATE FRM", "REPRICE_DATE_FROM"),
    ("REPRICE", "DATE THR", "REPRICE_DATE_TO"),
    ("REPRICE", "CPT/HCPCS", "REPRICE_CPT_HCPCS"),
    ("REPRICE", "CHARGES", "REPRICE_CHARGES"),
    ("REPRICE", "UNITS", "REPRICE_UNITS"),
    ("REPRICE", "ALLOWED/REPRICED", "ALLOWED_REPRICED"),
    ("REPRICE", "DISCOUNT/INELIGIBLE", "DISCOUNT_INELIGIBLE"),
    ("REPRICE", "DISCOUNT REASON CODE", "DISCOUNT_REASON_CODE"),
    ("REPRICE", "ICES/EDC REMARK CODE", "ICES_EDC_REMARK"),
    ("COBDOC", "APPVD", "MEDICARE_APPVD"),
    ("COBDOC", "PAID", "MEDICARE_PAID"),
    ("COBDOC", "NDC#", "NDC"),
]

_REPRICE_GROUP_LABEL = "REPRICE INFO, RENDERING PHYSICIAN, & NOTES"
_COBDOC_GROUP_LABEL = "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT"
_GROUP_LABELS = {"REPRICE": _REPRICE_GROUP_LABEL, "COBDOC": _COBDOC_GROUP_LABEL}


# ---------------------------------------------------------------------------
# Main — one row per service line, joined with its claim's demographics/totals
# (mirrors POPULATE_MAIN_SHEET, oShared.txt, computed directly instead of
# via Excel formulas)
# ---------------------------------------------------------------------------

MAIN_CLAIM_COLUMNS: list[tuple[str, str]] = [
    ("MACRO STATUS", "MACRO_STATUS"),
    ("OTHER NOTES", "CLAIM_NTE"),
    # Distinct key from MAIN_LINE_COLUMNS's "CLAIM CONTROL #" (which uses
    # plain "CLAIM_NO") — these are two separate Excel columns and must not
    # collide on one dict key, or blanking one blanks/overwrites the other.
    ("*CCN (Required)", "CCN_HEADER"),
    ("CLAIM TYPE", "CLAIM_TYPE"),
    ("PATIENT'S NAME", "PATIENT_NAME"),
    ("FROM SVDT", "FROM_SVDT"),
    ("THRU SVDT", "THRU_SVDT"),
    ("TOTAL CHARGE", "TOTAL_CHARGES"),
    ("TOTAL REPRICED", "TOTAL_REPRICED"),
    ("TOTAL DISCOUNT", "TOTAL_DISCOUNTS"),
    ("NO. OF SV LINES", "NO_OF_SVLINES"),
    ("XLRW LOC", "XLRW_LOC"),
]

MAIN_LINE_COLUMNS: list[tuple[str, str]] = [
    ("CLAIM CONTROL #", "CLAIM_NO"),
    ("DT SVC FROM", "DOS_FROM"),
    ("DT SVC TO", "DOS_TO"),
    ("CPT/HCPCS", "CPT_HCPCS"),
    ("TOS", "TOS"),
    ("DAYS OR UNITS", "DAYS_UNITS"),
    ("CHARGES", "CHARGES"),
    ("ALLOWED/REPRICED", "ALLOWED_REPRICED"),
    ("DISCOUNT/INELIGIBLE", "DISCOUNT_INELIGIBLE"),
    ("MOD 01", "MOD_A"),
    ("MOD 02", "MOD_B"),
    ("MOD 03", "MOD_C"),
    ("MOD 04", "MOD_D"),
    ("DX CODES", "DX_CODE"),
    ("PLACE OF SERVICE", "POS"),
    ("RESUBMISSION CODE", "RESUBMISSION_CODE"),
]


def _parse_date(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%m-%d-%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _build_main_rows(claims: list[dict], service_lines: list[dict]) -> list[dict]:
    """Recomputes POPULATE_MAIN_SHEET's join as plain Python dict rows."""
    lines_by_claim: dict[str, list[dict]] = {}
    for svl in service_lines:
        lines_by_claim.setdefault(svl.get("CLAIM_NO", ""), []).append(svl)

    rows: list[dict] = []
    for idx, claim in enumerate(claims, start=1):
        claim_no = claim.get("CLAIM_NO", "")
        own_lines = lines_by_claim.get(claim_no, [])

        dos_parsed = [(_parse_date(l.get("DOS_FROM", "")), l.get("DOS_FROM", "")) for l in own_lines]
        dos_parsed = [p for p in dos_parsed if p[0] is not None]
        thru_parsed = [(_parse_date(l.get("DOS_TO", "")), l.get("DOS_TO", "")) for l in own_lines]
        thru_parsed = [p for p in thru_parsed if p[0] is not None]

        claim_extra = {
            "CCN_HEADER": claim_no,
            "FROM_SVDT": min(dos_parsed)[1] if dos_parsed else "",
            "THRU_SVDT": max(thru_parsed)[1] if thru_parsed else "",
            "NO_OF_SVLINES": len(own_lines),
            # Sequence number of this claim within the run — the original
            # input's own worksheet row isn't carried through
            # claim_split_get_edi_details()'s output, so this is the
            # closest available stand-in for MAIN column S ("XLRW LOC").
            "XLRW_LOC": idx,
        }

        def _claim_block() -> dict:
            return {key: claim_extra.get(key, claim.get(key, "")) for _, key in MAIN_CLAIM_COLUMNS}

        def _line_block(svl: dict) -> dict:
            block = {key: svl.get(key, "") for _, key in MAIN_LINE_COLUMNS}
            block["TOS"] = ""  # manual-entry field, not produced by GET EDI DETAILS
            block["RESUBMISSION_CODE"] = claim.get("RESUBMISSION_CODE", "")
            return block

        if not own_lines:
            rows.append({**_claim_block(), **_line_block({})})
            continue

        # Claim-level columns (A:L — MACRO STATUS, CCN, PATIENT'S NAME,
        # TOTAL CHARGE, etc.) only get written on the claim's first line
        # row; subsequent lines leave them blank instead of repeating the
        # same values down every row.
        blank_claim_block = {key: "" for _, key in MAIN_CLAIM_COLUMNS}
        for i, svl in enumerate(own_lines):
            claim_block = _claim_block() if i == 0 else blank_claim_block
            rows.append({**claim_block, **_line_block(svl)})

    return rows


# ---------------------------------------------------------------------------
# Sheet writers
# ---------------------------------------------------------------------------

def _write_grouped_sheet(ws, columns: list[tuple[str | None, str, str]], rows: list[dict],
                          group_fills: dict[str, PatternFill] | None = None) -> None:
    group_fills = group_fills or {}
    ncols = len(columns)

    # Row 1: box-group headers, merged across contiguous same-group columns.
    # A `None` group is never merged with a neighbour (even another `None`
    # column right next to it) — each one gets its own row1:row2 vertical
    # merge instead, holding that column's own field label.
    col = 1
    while col <= ncols:
        group = columns[col - 1][0]
        span_end = col
        if group is not None:
            while span_end < ncols and columns[span_end][0] == group:
                span_end += 1
        label = _GROUP_LABELS.get(group, group) if group else columns[col - 1][1]
        ws.cell(row=1, column=col, value=label)
        if span_end > col:
            ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=span_end)
        if group is None:
            ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        fill = group_fills.get(group, _GROUP_FILL)
        for c in range(col, span_end + 1):
            top_cell = ws.cell(row=1, column=c)
            top_cell.fill = fill
            top_cell.font = _GROUP_FONT
            top_cell.alignment = _CENTER
            top_cell.border = _BORDER
        col = span_end + 1

    # Row 2: field labels (skip `None`-group columns — their label already
    # sits in the row1:row2 vertical merge written above)
    for c, (group, label, _key) in enumerate(columns, start=1):
        if group is None:
            continue
        cell = ws.cell(row=2, column=c, value=label)
        cell.fill = _LABEL_FILL
        cell.font = _LABEL_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER

    # Data rows
    for r, row in enumerate(rows, start=3):
        for c, (_group, _label, key) in enumerate(columns, start=1):
            cell = ws.cell(row=r, column=c, value=row.get(key, ""))
            cell.font = _DATA_FONT
            cell.border = _BORDER

    ws.freeze_panes = "A3"
    if rows:
        ws.auto_filter.ref = f"A2:{get_column_letter(ncols)}{len(rows) + 2}"
    _autosize(ws, ncols)


def _write_main_sheet(ws, rows: list[dict]) -> None:
    columns = MAIN_CLAIM_COLUMNS + MAIN_LINE_COLUMNS
    ncols = len(columns)
    n_claim_cols = len(MAIN_CLAIM_COLUMNS)

    for c, (label, _key) in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=c, value=label)
        cell.fill = _MAIN_LEFT_FILL if c <= n_claim_cols else _MAIN_RIGHT_FILL
        cell.font = _LABEL_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER

    for r, row in enumerate(rows, start=2):
        for c, (_label, key) in enumerate(columns, start=1):
            cell = ws.cell(row=r, column=c, value=row.get(key, ""))
            cell.font = _DATA_FONT
            cell.border = _BORDER

    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{len(rows) + 1}"
    _autosize(ws, ncols)


def build_workbook(claims: list[dict], service_lines: list[dict]) -> Workbook:
    """
    Builds the three-sheet workbook (Main / ClaimInfo / ClaimServiceLInes)
    from claim_split_get_edi_details()'s claims_df / service_lines_df
    (each a flat list of dicts). `claims` rows carrying a MACRO_STATUS from
    claim_split_run_batch's result (merged in by the caller) will show the
    split status instead of the fetch status.
    """
    wb = Workbook()
    wb.remove(wb.active)

    ws_main = wb.create_sheet("Main")
    _write_main_sheet(ws_main, _build_main_rows(claims, service_lines))

    ws_info = wb.create_sheet("ClaimInfo")
    _write_grouped_sheet(ws_info, CLAIMINFO_COLUMNS, claims)

    ws_svl = wb.create_sheet("ClaimServiceLInes")
    _write_grouped_sheet(
        ws_svl, CLAIMSVL_COLUMNS, service_lines,
        group_fills={"REPRICE": _REPRICE_FILL, "COBDOC": _COB_FILL},
    )

    wb.active = 0
    return wb


def write_workbook(claims: list[dict], service_lines: list[dict], path: str) -> str:
    build_workbook(claims, service_lines).save(path)
    return path
