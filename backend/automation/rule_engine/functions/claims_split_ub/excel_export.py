"""
Claims Split UB — Excel workbook export.

Writes the same three-sheet workbook shape the VBA macro produces on its
own MAIN / ClaimInfo / ClaimServiceLInes worksheets, following
claim_split_hcfa/excel_export.py's exact scaffolding (styling constants,
`_write_grouped_sheet`/`_write_main_sheet` generic writers, `build_workbook`/
`write_workbook` entry points — all unchanged from that module). Only the
column definitions below are UB-specific, traced to claims_split_ub's OWN
oReadPdf.txt/oShared.txt/oScratch.txt, not copied from the HCFA port.

Two things POPULATE_MAIN_SHEET (oShared.txt) does that this does NOT
reproduce, on purpose — same convention as claim_split_hcfa's own export:
  - MAIN column W ("TOS") is only populated live by GetClaim_TOS during a
    SCRATCH split (see cps_entry.py) — not by "02.GET EDI DETAILS" itself.
    Left blank here.
  - MAIN columns M:R (NEW_CERT/NEW_CCN/NEW_DOS/NEWBORN_TYPE/NON_NEWBORN_SEQ)
    are SCRATCH-mode *inputs* supplied before splitting, not something GET
    EDI DETAILS produces.
"""

from __future__ import annotations

from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Styling (identical to claim_split_hcfa/excel_export.py)
# ---------------------------------------------------------------------------

_THIN = Side(style="thin", color="B0B0B0")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_GROUP_FILL = PatternFill("solid", fgColor="1F3864")
_LABEL_FILL = PatternFill("solid", fgColor="BF9000")
_REPRICE_FILL = PatternFill("solid", fgColor="2E75B6")
_COB_FILL = PatternFill("solid", fgColor="548235")
_MAIN_LEFT_FILL = PatternFill("solid", fgColor="000000")
_MAIN_RIGHT_FILL = PatternFill("solid", fgColor="833C0B")

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

CLAIMINFO_COLUMNS: list[tuple[str | None, str, str]] = [
    (None, "CLAIM CONTROL NUMBER", "CLAIM_NO"),
    (None, "MACRO STATUS", "MACRO_STATUS"),
    ("BOX1", "PROVIDER NAME", "PROVIDER_NAME"),
    ("BOX1", "PROVIDER ADDR 1", "PROVIDER_ADDR1"),
    ("BOX1", "PROVIDER ADDR 2", "PROVIDER_ADDR2"),
    ("BOX1", "PROVIDER CITY", "PROVIDER_CITY"),
    ("BOX1", "PROVIDER STATE", "PROVIDER_STATE"),
    ("BOX1", "PROVIDER ZIP", "PROVIDER_ZIP"),
    ("BOX2", "BILLING NAME", "BILLING_NAME"),
    ("BOX2", "BILLING ADDR 1", "BILLING_ADDR1"),
    ("BOX2", "BILLING ADDR 2", "BILLING_ADDR2"),
    ("BOX2", "BILLING CITY", "BILLING_CITY"),
    ("BOX2", "BILLING STATE", "BILLING_STATE"),
    ("BOX2", "BILLING ZIP", "BILLING_ZIP"),
    ("BOX3A", "PAT CNTL #", "PAT_CNTL_NO"),
    ("BOX3B", "MED REC #", "MED_REC_NO"),
    ("BOX4", "TYPE OF BILL", "TYPE_OF_BILL"),
    ("BOX5", "FEDERAL TAX I.D. NUMBER", "FED_TAX_ID"),
    ("BOX6", "STATEMENT COVERS FROM", "PERIOD_COV_FROM"),
    ("BOX6", "STATEMENT COVERS THROUGH", "PERIOD_COV_TO"),
    # Box 7 is unlabeled/reserved on the real UB-04 form and the VBA never
    # extracts it either (oReadPdf.txt:23 — `'CI.Range("U" & rw) = ... 'Box7`
    # commented out) — kept blank so the box numbering stays contiguous,
    # same convention as BOX29/BOX30/BOX68/BOX73/BOX75 below.
    ("BOX7", "(UNUSED)", "BOX7_UNPOPULATED"),
    ("BOX8A", "PATIENT'S NAME", "PATIENT_NAME"),
    ("BOX9A", "PATIENT'S ADDRESS", "PATIENT_ADDR"),
    ("BOX10", "PATIENT'S BIRTHDATE", "PATIENT_DOB"),
    ("BOX11", "PATIENT'S SEX", "PATIENT_SEX"),
    ("BOX12", "ADMISSION DATE", "ADMISSION_DATE"),
    ("BOX13", "ADMISSION HR", "ADMISSION_HR"),
    ("BOX14", "ADMISSION TYPE", "ADMISSION_TYPE"),
    ("BOX15", "ADMISSION SRC", "ADMISSION_SRC"),
    ("BOX16", "DHR", "DHR"),
    ("BOX17", "STAT", "STAT"),
    ("CONDITION CODES BOX(18-28)", "18", "COND_CODE_18"), ("CONDITION CODES BOX(18-28)", "19", "COND_CODE_19"),
    ("CONDITION CODES BOX(18-28)", "20", "COND_CODE_20"), ("CONDITION CODES BOX(18-28)", "21", "COND_CODE_21"),
    ("CONDITION CODES BOX(18-28)", "22", "COND_CODE_22"), ("CONDITION CODES BOX(18-28)", "23", "COND_CODE_23"),
    ("CONDITION CODES BOX(18-28)", "24", "COND_CODE_24"), ("CONDITION CODES BOX(18-28)", "25", "COND_CODE_25"),
    ("CONDITION CODES BOX(18-28)", "26", "COND_CODE_26"), ("CONDITION CODES BOX(18-28)", "27", "COND_CODE_27"),
    ("CONDITION CODES BOX(18-28)", "28", "COND_CODE_28"),
    # Box 29 is a DIFFERENT field (Accident State), not another condition
    # code — oReadPdf.txt's own comment on this coordinate is
    # 'Box29_ACDT_State, distinct from the Box18-28 condition-code slots
    # above. Kept its own single-column group rather than folding it into
    # "CONDITION CODES BOX(18-28)".
    ("BOX29", "ACDT STATE", "COND_CODE_29"),
    # Box 30 is unlabeled/reserved on the real UB-04 form and the VBA never
    # extracts it either (oReadPdf.txt: `'CI.Range("AR" & rw) = ... 'Box30`
    # — commented out) — kept as a blank placeholder column so the box
    # numbering stays contiguous with the reference workbook's own layout.
    ("BOX30", "(UNUSED)", "BOX30_UNPOPULATED"),
    ("OCCURRENCE A (31-34)", "31 CODE", "OCC_A_31_CODE"), ("OCCURRENCE A (31-34)", "31 DATE", "OCC_A_31_DATE"),
    ("OCCURRENCE A (31-34)", "32 CODE", "OCC_A_32_CODE"), ("OCCURRENCE A (31-34)", "32 DATE", "OCC_A_32_DATE"),
    ("OCCURRENCE A (31-34)", "33 CODE", "OCC_A_33_CODE"), ("OCCURRENCE A (31-34)", "33 DATE", "OCC_A_33_DATE"),
    ("OCCURRENCE A (31-34)", "34 CODE", "OCC_A_34_CODE"), ("OCCURRENCE A (31-34)", "34 DATE", "OCC_A_34_DATE"),
    ("OCC SPAN A (35-36)", "35 CODE", "OCC_SPAN_A_35_CODE"),
    ("OCC SPAN A (35-36)", "35 FROM", "OCC_SPAN_A_35_FROM"),
    ("OCC SPAN A (35-36)", "35 THRU", "OCC_SPAN_A_35_THRU"),
    ("OCC SPAN A (35-36)", "36 CODE", "OCC_SPAN_A_36_CODE"),
    ("OCC SPAN A (35-36)", "36 FROM", "OCC_SPAN_A_36_FROM"),
    ("OCC SPAN A (35-36)", "36 THRU", "OCC_SPAN_A_36_THRU"),
    ("BOX37A", "37A", "BOX37A"),
    # Blank, no box number in the VBA at all (oReadPdf.txt:62 —
    # `'CI.Range("BH" & rw) =`, no comment) — kept as a placeholder column
    # so the occurrence-B block below lines up with the reference workbook.
    (None, "(UNUSED)", "BOX_BH_UNPOPULATED"),
    ("OCCURRENCE B (31-34)", "31 CODE", "OCC_B_31_CODE"), ("OCCURRENCE B (31-34)", "31 DATE", "OCC_B_31_DATE"),
    ("OCCURRENCE B (31-34)", "32 CODE", "OCC_B_32_CODE"), ("OCCURRENCE B (31-34)", "32 DATE", "OCC_B_32_DATE"),
    ("OCCURRENCE B (31-34)", "33 CODE", "OCC_B_33_CODE"), ("OCCURRENCE B (31-34)", "33 DATE", "OCC_B_33_DATE"),
    ("OCCURRENCE B (31-34)", "34 CODE", "OCC_B_34_CODE"), ("OCCURRENCE B (31-34)", "34 DATE", "OCC_B_34_DATE"),
    ("OCC SPAN B (35-36)", "35 CODE", "OCC_SPAN_B_35_CODE"),
    ("OCC SPAN B (35-36)", "35 FROM", "OCC_SPAN_B_35_FROM"),
    ("OCC SPAN B (35-36)", "35 THRU", "OCC_SPAN_B_35_THRU"),
    ("OCC SPAN B (35-36)", "36 CODE", "OCC_SPAN_B_36_CODE"),
    ("OCC SPAN B (35-36)", "36 FROM", "OCC_SPAN_B_36_FROM"),
    ("OCC SPAN B (35-36)", "36 THRU", "OCC_SPAN_B_36_THRU"),
    ("BOX37B", "37B", "BOX37B"),
    ("BOX38", "NAME", "BOX38_NAME"),
    ("BOX38", "ADDRESS 1", "BOX38_ADDR1"),
    ("BOX38", "ADDRESS 2", "BOX38_ADDR2"),
    ("BOX38", "CITY", "BOX38_CITY"),
    ("BOX38", "STATE", "BOX38_STATE"),
    ("BOX38", "ZIPCODE", "BOX38_ZIP"),
    ("BOX39A", "VALUE CODE", "VALUE_39A_CODE"), ("BOX39A", "VALUE CODE AMOUNT", "VALUE_39A_AMT"),
    ("BOX39B", "VALUE CODE", "VALUE_39B_CODE"), ("BOX39B", "VALUE CODE AMOUNT", "VALUE_39B_AMT"),
    ("BOX39C", "VALUE CODE", "VALUE_39C_CODE"), ("BOX39C", "VALUE CODE AMOUNT", "VALUE_39C_AMT"),
    ("BOX39D", "VALUE CODE", "VALUE_39D_CODE"), ("BOX39D", "VALUE CODE AMOUNT", "VALUE_39D_AMT"),
    ("BOX40A", "VALUE CODE", "VALUE_40A_CODE"), ("BOX40A", "VALUE CODE AMOUNT", "VALUE_40A_AMT"),
    ("BOX40B", "VALUE CODE", "VALUE_40B_CODE"), ("BOX40B", "VALUE CODE AMOUNT", "VALUE_40B_AMT"),
    ("BOX40C", "VALUE CODE", "VALUE_40C_CODE"), ("BOX40C", "VALUE CODE AMOUNT", "VALUE_40C_AMT"),
    ("BOX40D", "VALUE CODE", "VALUE_40D_CODE"), ("BOX40D", "VALUE CODE AMOUNT", "VALUE_40D_AMT"),
    ("BOX41A", "VALUE CODE", "VALUE_41A_CODE"), ("BOX41A", "VALUE CODE AMOUNT", "VALUE_41A_AMT"),
    ("BOX41B", "VALUE CODE", "VALUE_41B_CODE"), ("BOX41B", "VALUE CODE AMOUNT", "VALUE_41B_AMT"),
    ("BOX41C", "VALUE CODE", "VALUE_41C_CODE"), ("BOX41C", "VALUE CODE AMOUNT", "VALUE_41C_AMT"),
    ("BOX41D", "VALUE CODE", "VALUE_41D_CODE"), ("BOX41D", "VALUE CODE AMOUNT", "VALUE_41D_AMT"),
    ("PAYER A (50-55)", "NAME", "PAYER_A_NAME"), ("PAYER A (50-55)", "PLAN ID", "PAYER_A_PLAN_ID"),
    ("PAYER A (50-55)", "REL INFO", "PAYER_A_REL_INFO"), ("PAYER A (50-55)", "ASG BEN", "PAYER_A_ASG_BEN"),
    ("PAYER A (50-55)", "PRIOR PAYMENTS", "PAYER_A_PRIOR_PMT"), ("PAYER A (50-55)", "EST AMOUNT DUE", "PAYER_A_EST_DUE"),
    ("PAYER B (50-55)", "NAME", "PAYER_B_NAME"), ("PAYER B (50-55)", "PLAN ID", "PAYER_B_PLAN_ID"),
    ("PAYER B (50-55)", "REL INFO", "PAYER_B_REL_INFO"), ("PAYER B (50-55)", "ASG BEN", "PAYER_B_ASG_BEN"),
    ("PAYER B (50-55)", "PRIOR PAYMENTS", "PAYER_B_PRIOR_PMT"), ("PAYER B (50-55)", "EST AMOUNT DUE", "PAYER_B_EST_DUE"),
    ("PAYER C (50-55)", "NAME", "PAYER_C_NAME"), ("PAYER C (50-55)", "PLAN ID", "PAYER_C_PLAN_ID"),
    ("PAYER C (50-55)", "REL INFO", "PAYER_C_REL_INFO"), ("PAYER C (50-55)", "ASG BEN", "PAYER_C_ASG_BEN"),
    ("PAYER C (50-55)", "PRIOR PAYMENTS", "PAYER_C_PRIOR_PMT"), ("PAYER C (50-55)", "EST AMOUNT DUE", "PAYER_C_EST_DUE"),
    ("BOX56", "NPI", "NPI_56"),
    ("BOX57", "PRIMARY", "BOX57"), ("BOX57", "OTHER", "BOX57_OTHER"), ("BOX57", "PRV ID", "BOX57_PRV_ID"),
    ("INSURED A (58-62)", "NAME", "INSURED_A_NAME"), ("INSURED A (58-62)", "P REL", "INSURED_A_P_REL"),
    ("INSURED A (58-62)", "UNIQUE ID", "INSURED_A_UNIQUE_ID"), ("INSURED A (58-62)", "GROUP NAME", "INSURED_A_GROUP_NAME"),
    ("INSURED A (58-62)", "GROUP NO", "INSURED_A_GROUP_NO"),
    ("INSURED B (58-62)", "NAME", "INSURED_B_NAME"), ("INSURED B (58-62)", "P REL", "INSURED_B_P_REL"),
    ("INSURED B (58-62)", "UNIQUE ID", "INSURED_B_UNIQUE_ID"), ("INSURED B (58-62)", "GROUP NAME", "INSURED_B_GROUP_NAME"),
    ("INSURED B (58-62)", "GROUP NO", "INSURED_B_GROUP_NO"),
    ("INSURED C (58-62)", "NAME", "INSURED_C_NAME"), ("INSURED C (58-62)", "P REL", "INSURED_C_P_REL"),
    ("INSURED C (58-62)", "UNIQUE ID", "INSURED_C_UNIQUE_ID"), ("INSURED C (58-62)", "GROUP NAME", "INSURED_C_GROUP_NAME"),
    ("INSURED C (58-62)", "GROUP NO", "INSURED_C_GROUP_NO"),
    ("TREATMENT AUTH (63)", "A", "TREATMENT_AUTH_A"), ("TREATMENT AUTH (63)", "B", "TREATMENT_AUTH_B"),
    ("TREATMENT AUTH (63)", "C", "TREATMENT_AUTH_C"),
    ("DOC CONTROL # (64)", "A", "DOC_CONTROL_NO_A"), ("DOC CONTROL # (64)", "B", "DOC_CONTROL_NO_B"),
    ("DOC CONTROL # (64)", "C", "DOC_CONTROL_NO_C"),
    ("EMPLOYER NAME (65)", "A", "EMPLOYER_NAME_A"), ("EMPLOYER NAME (65)", "B", "EMPLOYER_NAME_B"),
    ("EMPLOYER NAME (65)", "C", "EMPLOYER_NAME_C"),
    ("BOX66", "DX VERSION QUALIFIER", "BOX66_DX_VERSION"),
    ("BOX67", "PRINCIPAL", "DX_PRIMARY"),
    ("BOX67", "A", "DX_67A"), ("BOX67", "B", "DX_67B"), ("BOX67", "C", "DX_67C"),
    ("BOX67", "D", "DX_67D"), ("BOX67", "E", "DX_67E"), ("BOX67", "F", "DX_67F"),
    ("BOX67", "G", "DX_67G"), ("BOX67", "H", "DX_67H"), ("BOX67", "I", "DX_67I"),
    ("BOX67", "J", "DX_67J"), ("BOX67", "K", "DX_67K"), ("BOX67", "L", "DX_67L"),
    ("BOX67", "M", "DX_67M"), ("BOX67", "N", "DX_67N"), ("BOX67", "O", "DX_67O"),
    ("BOX67", "P", "DX_67P"), ("BOX67", "Q", "DX_67Q"),
    # Box 68 ("Extra Boxes") is unlabeled/reserved and the VBA never
    # extracts it (oReadPdf.txt:169 — `'CI.Range("FO" & rw) ='Box68 -
    # Extra Boxes`, commented out).
    ("BOX68", "(UNUSED)", "BOX68_UNPOPULATED"),
    ("BOX69", "ADMIT DX", "DX_ADMIT_69"),
    ("BOX70A", "PATIENT DX", "DX_PATIENT_REASON_A_70"),
    ("BOX70B", "PATIENT DX", "DX_PATIENT_REASON_B_70"),
    ("BOX70C", "PATIENT DX", "DX_PATIENT_REASON_C_70"),
    ("BOX71", "PPS CODE", "PPS_CODE_71"),
    ("BOX72A", "ECI", "ECI_A_72"), ("BOX72B", "ECI", "ECI_B_72"), ("BOX72C", "ECI", "ECI_C_72"),
    # Box 73 is unlabeled/reserved and the VBA never extracts it either
    # (oReadPdf.txt:178 — `'CI.Range("FX" & rw) = ... 'Box73`, commented out).
    ("BOX73", "(UNUSED)", "BOX73_UNPOPULATED"),
    ("BOX74", "PRINCIPAL PROCEDURE CODE", "PRINCIPAL_PROC_CODE_74"),
    ("BOX74", "PRINCIPAL PROCEDURE DATE", "PRINCIPAL_PROC_DATE_74"),
    ("BOX74A", "OTHER PROCEDURE CODE", "OTHER_PROC_A_CODE_74"), ("BOX74A", "OTHER PROCEDURE DATE", "OTHER_PROC_A_DATE_74"),
    ("BOX74B", "OTHER PROCEDURE CODE", "OTHER_PROC_B_CODE_74"), ("BOX74B", "OTHER PROCEDURE DATE", "OTHER_PROC_B_DATE_74"),
    ("BOX74C", "OTHER PROCEDURE CODE", "OTHER_PROC_C_CODE_74"), ("BOX74C", "OTHER PROCEDURE DATE", "OTHER_PROC_C_DATE_74"),
    ("BOX74D", "OTHER PROCEDURE CODE", "OTHER_PROC_D_CODE_74"), ("BOX74D", "OTHER PROCEDURE DATE", "OTHER_PROC_D_DATE_74"),
    ("BOX74E", "OTHER PROCEDURE CODE", "OTHER_PROC_E_CODE_74"), ("BOX74E", "OTHER PROCEDURE DATE", "OTHER_PROC_E_DATE_74"),
    # Box 75 is unlabeled/reserved and the VBA never extracts it either
    # (oReadPdf.txt:191 — `'CI.Range("GK" & rw) =`, no comment at all).
    ("BOX75", "(UNUSED)", "BOX75_UNPOPULATED"),
    ("BOX76", "NPI", "ATTENDING_NPI_76"), ("BOX76", "QUAL", "ATTENDING_QUAL_76"),
    ("BOX76", "LAST", "ATTENDING_LAST_76"), ("BOX76", "FIRST", "ATTENDING_FIRST_76"),
    ("BOX77", "NPI", "OPERATING_NPI_77"), ("BOX77", "QUAL", "OPERATING_QUAL_77"),
    ("BOX77", "LAST", "OPERATING_LAST_77"), ("BOX77", "FIRST", "OPERATING_FIRST_77"),
    ("BOX78", "NPI", "OTHER1_NPI_78"), ("BOX78", "QUAL", "OTHER1_QUAL_78"),
    ("BOX78", "LAST", "OTHER1_LAST_78"), ("BOX78", "FIRST", "OTHER1_FIRST_78"),
    ("BOX79", "NPI", "OTHER2_NPI_79"), ("BOX79", "QUAL", "OTHER2_QUAL_79"),
    ("BOX79", "LAST", "OTHER2_LAST_79"), ("BOX79", "FIRST", "OTHER2_FIRST_79"),
    # This whole tail section's order/grouping is taken directly from the
    # reference workbook (its own header row), not the VBA write order in
    # Main.txt/oReadPdf.txt (which writes these same fields into INF cells
    # in a different sequence) — matches what the user actually sees.
    ("ADDITIONAL REFERENCES", "TOTAL CHARGES", "TOTAL_CHARGES"),
    ("ADDITIONAL REFERENCES", "TOTAL REPRICED", "TOTAL_REPRICED"),
    ("ADDITIONAL REFERENCES", "TOTAL DISCOUNTS", "TOTAL_DISCOUNTS"),
    ("ADDITIONAL REFERENCES", "RE-PRICE IND", "REPRICED_IND"),
    ("MEDICARE/MEDICAID COB INFORMATION", "DEDUCTIBLE", "COB_DEDUCTIBLE"),
    ("MEDICARE/MEDICAID COB INFORMATION", "CO INSURANCE", "COB_COINSURANCE"),
    ("MEDICARE/MEDICAID COB INFORMATION", "CALCULATED APPRV AMT", "COB_CALC_APPROVED_AMT"),
    ("MEDICARE/MEDICAID COB INFORMATION", "PAID", "COB_PAID_TOTAL"),
    ("MEDICARE/MEDICAID COB INFORMATION", "PATIENT RESPN", "COB_PATIENT_RESPONSIBILITY"),
    ("MEDICARE/MEDICAID COB INFORMATION", "NON COVERED", "COB_NON_COVERED"),
    ("MEDICARE/MEDICAID COB INFORMATION", "CONTRACTUAL", "COB_CONTRACTUAL"),
    ("MEDICARE/MEDICAID COB INFORMATION", "CLAIM ADJUSTMENT", "COB_ADJUSTMENT_DETAIL"),
    # The reference workbook's own header text for this field is "MEMBER
    # ID", not "MEDICARE ID" — kept the dict key as COB_MEDICARE_ID (it's
    # what Medicare_Medicaid_Cob_Information's "Medicare ID" KeyPattern
    # search populates) but matched the display label the user actually sees.
    ("MEDICARE/MEDICAID COB INFORMATION", "MEMBER ID", "COB_MEDICARE_ID"),
    ("MEDICARE/MEDICAID COB INFORMATION", "HIC NUMBER", "HIC_NUMBER"),
    # HP in the original: read as an input on the CPS325 screen (Scratch Not
    # Online mode, oScratchNotOnline:132) but no extraction routine in
    # oReadPdf.txt ever writes it — always blank in the real macro too. See
    # pdf_extract.py's module docstring.
    ("FOR PRV SELECTION", "PROVIDER INTERNAL MANUAL ID", "BOX_HP_UNPOPULATED"),
    (None, "RE-PRICED BY", "REPRICED_BY"),
    (None, "OTHER INSURANCE TYPE", "COB_OTHER_INS_TYPE"),
    (None, "METHOD", "METHOD_INFO"),
    (None, "TIMELY FILING", "TIMELY_FILING"),
    (None, "CLAIM NTE", "CLAIM_NTE"),
]


# ---------------------------------------------------------------------------
# ClaimServiceLInes — one row per service line
# ---------------------------------------------------------------------------

CLAIMSVL_COLUMNS: list[tuple[str | None, str, str]] = [
    (None, "CLAIM CONTROL NUMBER", "CLAIM_NO"),
    (None, "REV CD", "REV_CD"),
    (None, "DESCRIPTION", "DESCRIPTION"),
    (None, "HCPCS/RATE/HIPPS CODE", "HCPCS_CODE"),
    ("MODIFIERS", "01", "MOD_A"), ("MODIFIERS", "02", "MOD_B"),
    ("MODIFIERS", "03", "MOD_C"), ("MODIFIERS", "04", "MOD_D"),
    (None, "SERV DATE", "SERV_DATE"),
    (None, "SERV UNITS", "SERV_UNITS"),
    (None, "TOTAL CHARGES", "TOTAL_CHARGES"),
    (None, "NON-COVERED CHARGES", "NON_COVERED_CHARGES"),
    (None, "BOX49", "BOX49"),
    ("REPRICE", "DATE FRM", "REPRICE_DATE_FROM"),
    ("REPRICE", "DATE THR", "REPRICE_DATE_TO"),
    ("REPRICE", "HCPCS", "REPRICE_HCPCS"),
    ("REPRICE", "CHARGES", "REPRICE_CHARGES"),
    ("REPRICE", "UNITS", "REPRICE_UNITS"),
    ("REPRICE", "REPRICED", "REPRICED"),
    ("REPRICE", "DISCOUNT", "DISCOUNT"),
    ("REPRICE", "DISCOUNT REASON", "DISCOUNT_REASON"),
    ("COBDOC", "DATE FRM", "COB_DATE_FROM"),
    ("COBDOC", "DATE THR", "COB_DATE_TO"),
    ("COBDOC", "CPT/HCPCS", "COB_CPT_HCPCS"),
    ("COBDOC", "CHARGES", "COB_CHARGES"),
    ("COBDOC", "PTNT RSPNS", "COB_PTNT_RESP"),
    ("COBDOC", "DED", "COB_DEDUCTIBLE"),
    ("COBDOC", "APPVD", "COB_APPVD"),
    ("COBDOC", "PAID", "COB_PAID"),
]

_REPRICE_GROUP_LABEL = "REPRICE INFO, RENDERING PHYSICIAN, & NOTES"
_COBDOC_GROUP_LABEL = "MEDICARE/MEDICAID/COB SUPPORT DOCUMENT"
_GROUP_LABELS = {"REPRICE": _REPRICE_GROUP_LABEL, "COBDOC": _COBDOC_GROUP_LABEL}


# ---------------------------------------------------------------------------
# Main — one row per service line, joined with its claim's demographics/totals
# (mirrors Populate_Main_Sheet, oShared.txt, computed directly instead of via
# Excel formulas)
# ---------------------------------------------------------------------------

MAIN_CLAIM_COLUMNS: list[tuple[str, str]] = [
    ("MACRO STATUS", "MACRO_STATUS"),
    ("OTHER NOTES", "NOTES"),
    ("*CCN (Required)", "CCN_HEADER"),
    ("CLAIM TYPE", "CLAIM_TYPE"),
    ("PATIENT'S NAME", "PATIENT_NAME"),
    ("FROM SVDT", "FROM_SVDT"),
    ("THRU SVDT", "THRU_SVDT"),
    ("TOTAL CHARGE", "TOTAL_CHARGES"),
    ("TOTAL REPRICED", "TOTAL_REPRICED"),
    ("TOTAL DISCOUNT", "TOTAL_DISCOUNTS"),
    ("NO. OF SV LINES", "TOTAL_SVLINES"),
    ("XLRW LOC", "XLRW_LOC"),
]

MAIN_LINE_COLUMNS: list[tuple[str, str]] = [
    ("CLAIM CONTROL #", "CLAIM_NO"),
    ("SV DATE", "SERV_DATE"),
    ("RV CODE", "REV_CD"),
    ("HCPCS CODE", "HCPCS_CODE"),
    ("TOS", "TOS"),
    ("UNITS/BU", "SERV_UNITS"),
    ("CHARGES", "TOTAL_CHARGES"),
    ("REPRICED", "REPRICED"),
    ("DISCOUNT", "DISCOUNT"),
    ("MOD 01", "MOD_A"),
    ("MOD 02", "MOD_B"),
    ("MOD 03", "MOD_C"),
    ("MOD 04", "MOD_D"),
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
    """Recomputes Populate_Main_Sheet's join as plain Python dict rows."""
    lines_by_claim: dict[str, list[dict]] = {}
    for svl in service_lines:
        lines_by_claim.setdefault(svl.get("CLAIM_NO", ""), []).append(svl)

    rows: list[dict] = []
    for idx, claim in enumerate(claims, start=1):
        claim_no = claim.get("CLAIM_NO", "")
        # Mirrors Populate_Main_Sheet's own 2-key sort (oShared.txt:112-115)
        # — SV Date then RV Code, both ascending (the commented-out 3rd sort
        # key, HCPCS descending, was left disabled in the VBA itself —
        # "Added 2023.04.25" then commented back out — not reproduced here
        # either, matching what actually ships).
        own_lines = sorted(
            lines_by_claim.get(claim_no, []),
            key=lambda l: (l.get("SERV_DATE", ""), l.get("REV_CD", "")),
        )

        dos_parsed = [(_parse_date(l.get("SERV_DATE", "")), l.get("SERV_DATE", "")) for l in own_lines]
        dos_parsed = [p for p in dos_parsed if p[0] is not None]

        claim_extra = {
            "CCN_HEADER": claim_no,
            # FROM SVDT / THRU SVDT (MAIN columns F/G) aren't extracted
            # fields at all — mirrors claim_split_hcfa's own Main sheet
            # builder: the earliest/latest SERV_DATE across this claim's own
            # service lines, not anything read off the PDF directly.
            "FROM_SVDT": min(dos_parsed)[1] if dos_parsed else "",
            "THRU_SVDT": max(dos_parsed)[1] if dos_parsed else "",
            "TOTAL_SVLINES": len(own_lines),
            # Sequence number of this claim within the run — the original
            # input's own worksheet row isn't carried through
            # claims_split_ub_get_edi_details()'s output, so this is the
            # closest available stand-in for MAIN column L ("XLRW LOC").
            "XLRW_LOC": idx,
        }

        def _claim_block() -> dict:
            return {key: claim_extra.get(key, claim.get(key, "")) for _, key in MAIN_CLAIM_COLUMNS}

        def _line_block(svl: dict) -> dict:
            block = {key: svl.get(key, "") for _, key in MAIN_LINE_COLUMNS}
            block["TOS"] = svl.get("TOS", "")  # only populated once GetClaim_TOS has run (SCRATCH split) — see module docstring
            return block

        if not own_lines:
            rows.append({**_claim_block(), **_line_block({})})
            continue

        blank_claim_block = {key: "" for _, key in MAIN_CLAIM_COLUMNS}
        for i, svl in enumerate(own_lines):
            claim_block = _claim_block() if i == 0 else blank_claim_block
            rows.append({**claim_block, **_line_block(svl)})

    return rows


# ---------------------------------------------------------------------------
# Sheet writers (identical scaffolding to claim_split_hcfa/excel_export.py)
# ---------------------------------------------------------------------------

def _write_grouped_sheet(ws, columns: list[tuple[str | None, str, str]], rows: list[dict],
                          group_fills: dict[str, PatternFill] | None = None) -> None:
    group_fills = group_fills or {}
    ncols = len(columns)

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

    for c, (group, label, _key) in enumerate(columns, start=1):
        if group is None:
            continue
        cell = ws.cell(row=2, column=c, value=label)
        cell.fill = _LABEL_FILL
        cell.font = _LABEL_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER

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
    from claims_split_ub_get_edi_details()'s claims_df / service_lines_df
    (each a flat list of dicts). `claims` rows carrying a MACRO_STATUS from
    claims_split_ub_run_batch's result (merged in by the caller) will show
    the split status instead of the fetch status.
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
