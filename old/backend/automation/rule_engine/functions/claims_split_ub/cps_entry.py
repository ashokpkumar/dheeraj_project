"""
Claims Split UB — PART 2: keying split drafts into the CPS mainframe.

Ports oScratch.txt, oNonScratch.txt and oScratchNotOnline. This is the
"typing into the terminal" half of the macro — nothing here talks to the
web; the claim data it types was already fetched and parsed by
web_claims.py / pdf_extract.py (PART 1) before any of these functions run.

Each of the three split routines below is a straight port of its VBA
namesake and returns a small status dict — `{"status": "DONE."/"CANCELLED.",
"notes": "...", "drafts_created": n}` — same convention as
claim_split_hcfa/cps_entry.py, instead of writing MAIN columns A/B.

Shared shape used throughout:
  claim_row      dict  — MAIN claim-block fields (CLAIM_NO, NEW_CERT,
                          NEW_CCN, NEW_DOS, NON_NEWBORN_SEQ, NEWBORN_TYPE)
  demographics   dict  — from pdf_extract.extract_demographics()
  service_lines  list[dict] — from pdf_extract.extract_service_lines(),
                          already repriced by extract_claim(); get_claim_tos()
                          / get_cps_discounts() below further enrich these
                          with POS/TOS/DISCOUNT read live off the mainframe
  settings       dict  — the run-level options (mirrors the checkboxes/
                          dropdowns on the VBA MAIN sheet): two_lines_per_draft,
                          get_cps_discount, split_grouping
                          ("BY DATE OF SERVICE" is the only grouping mode
                          this macro's MAIN X3 dropdown actually branches on
                          — unlike claim_split_hcfa, there is no "BY
                          DIAGNOSIS" Case in oScratch.txt/oNonScratch.txt at
                          all; any other value means no date-based grouping
                          boundary, only the POS/CCN boundaries below)

*** UNVERIFIED AGAINST A REAL MAINFRAME SESSION *** — same risk class as
claim_split_hcfa/cps_entry.py: every screen row/column offset below is
ported as literally as possible from oScratch.txt/oNonScratch.txt/
oScratchNotOnline, but has not been exercised against a live CPS session.
get_claim_tos()/get_cps_discounts() in particular are the least confident
part of this file — they page through the ORIGINAL claim's already-keyed
drafts on-screen and match each existing line back to `service_lines` by
(CLAIM_NO, REV_CD, HCPCS_CODE, SERV_DATE), mirroring an Excel AutoFilter the
VBA uses that has no direct screen-scraping analog to cross-check against.
"""

from __future__ import annotations

from .utils import is_screen, place_value, remove_value, send_enter, send_pf

BYPASS_CODE = "001"
INEL_CODE = "908"
RLS_CODE = "60"
LST_RLS = "N"
PEND_RSN = "o99"
FLUP_DAYS = "001"
PAYEE = "0"


# ---------------------------------------------------------------------------
# ClaimPgCount / GetClaim_TOS / GetCPS_Discounts — scrape the ORIGINAL
# claim's already-keyed drafts before splitting
# ---------------------------------------------------------------------------

def claim_pg_count(screen, ccn: str) -> int:
    """
    Mirrors ClaimPgCount VBA. Assumes the CPS500-style claim-draft-list
    screen for `ccn` is already on screen. Counts pages by following
    "MORE DATA" via Pf11, then returns to the CCN-entry screen (Pf9 +
    re-enter ccn + Enter) so the caller lands back where the VBA does.

    NOTE: the VBA's inner `For i = 6 To 18 Step 2: If ... Exit For: Next i`
    (oNonScratch.txt:7-9) reads each draft-slot row but never uses the
    result for anything — no accumulator, no branch depends on it — a
    no-op in the original. Not ported for that reason (confirmed, not an
    oversight).
    """
    pg_cnt = 0
    while True:
        pg_cnt += 1
        if "MORE DATA" not in (screen.GetString(20, 2, 60) or "").upper():
            break
        send_pf(screen, 11)
    send_pf(screen, 9)
    place_value(screen, ccn, 8, 15)
    send_enter(screen)
    return pg_cnt


def _scan_original_claim_drafts(screen, ccn: str, service_lines: list[dict], *, write_pos_tos: bool) -> int:
    """
    Shared body of GetClaim_TOS / GetCPS_Discounts VBA — both page through
    every existing draft of `ccn` (assumes the CPS500-style draft-list
    screen is already on screen) and, for each populated service line on
    each opened draft, match it against `service_lines` by (CLAIM_NO,
    REV_CD, HCPCS_CODE, SERV_DATE) — mirroring the VBA's Excel AutoFilter on
    those four MAIN columns (S/U/V/T).

    A match always gets its live CPS discount captured into `DISCOUNT`
    ("amt-code", gated on the line's screen charge equalling the matched
    service line's TOTAL_CHARGES, same `Format(...,"0.00") = ...` check both
    VBA subs share). `write_pos_tos=True` (GetClaim_TOS only) additionally
    writes `POS`/`TOS` unconditionally on every (CCN, REV_CD, HCPCS_CODE,
    SERV_DATE) match, split from the draft-header POS + per-line TOS.

    Returns the count of this ccn's service lines still missing POS/TOS
    (GetClaim_TOS's real return value — the cancel-gate in
    ub_scratch_split()) when write_pos_tos=True; when False (GetCPS_Discounts)
    the count is still computed the same way but the caller ignores it,
    matching the VBA (its return value is never checked by the one call site
    in UB_NonScratch_Split).
    """
    pg_cnt = claim_pg_count(screen, ccn)
    p = 1
    for pg in range(1, pg_cnt + 1):
        while p < pg:
            send_pf(screen, 11)
            p += 1
        for r in (6, 8, 10, 12, 14, 16, 18):
            draft_id = (screen.GetString(r, 2, 2) or "").strip()
            if not draft_id:
                break
            place_value(screen, draft_id, 3, 26)
            send_enter(screen)
            send_enter(screen)

            for i in (6, 7, 8, 9):
                if not (screen.GetString(i, 3, 4) or "").strip():
                    continue
                rev_cd = (screen.GetString(i, 3, 4) or "").strip()
                hcpcs = (screen.GetString(i, 8, 5) or "").strip()
                raw_date = (screen.GetString(i, 17, 6) or "").strip()
                serv_date = f"{raw_date[0:2]}/{raw_date[2:4]}/{raw_date[4:6]}" if len(raw_date) == 6 else raw_date
                header_pos = (screen.GetString(1, 26, 2) or "").strip()
                line_tos = (screen.GetString(i, 14, 2) or "").strip()
                screen_charge = (screen.GetString(i, 40, 11) or "").strip()

                for svl in service_lines:
                    if not (
                        svl.get("CLAIM_NO") == ccn
                        and svl.get("REV_CD") == rev_cd
                        and svl.get("HCPCS_CODE") == hcpcs
                        and svl.get("SERV_DATE") == serv_date
                    ):
                        continue
                    if write_pos_tos:
                        svl["POS"] = header_pos
                        svl["TOS"] = line_tos
                    try:
                        matched_charge = f"{float(svl.get('TOTAL_CHARGES') or 0):.2f}"
                    except ValueError:
                        matched_charge = None
                    if matched_charge == screen_charge:
                        amt = (screen.GetString(i + 6, 2, 11) or "").strip() or "0.00"
                        code = (screen.GetString(i + 6, 14, 3) or "").strip() or "001"
                        svl["DISCOUNT"] = f"{amt}-{code}"

            send_pf(screen, 9)
            place_value(screen, ccn, 8, 15)
            send_enter(screen)
            p = 1
            while p < pg:
                send_pf(screen, 11)
                p += 1

    missing = sum(
        1 for svl in service_lines
        if svl.get("CLAIM_NO") == ccn and not svl.get("POS")
    )
    return missing


def get_claim_tos(screen, ccn: str, service_lines: list[dict]) -> int:
    """Mirrors GetClaim_TOS VBA. Returns the count of `ccn`'s service lines still missing POS/TOS."""
    return _scan_original_claim_drafts(screen, ccn, service_lines, write_pos_tos=True)


def get_cps_discounts(screen, ccn: str, service_lines: list[dict]) -> int:
    """Mirrors GetCPS_Discounts VBA. Return value is not used by the one VBA call site (UB_NonScratch_Split)."""
    return _scan_original_claim_drafts(screen, ccn, service_lines, write_pos_tos=False)


def find_03_04_tod(screen) -> bool:
    """Mirrors Find_03_04_TOD VBA — True if any condition on the (first) page has TOD 03 or 04."""
    for i in range(4, 19, 2):
        if not (screen.GetString(i, 4, 4) or "").strip():
            break
        if (screen.GetString(i, 34, 2) or "").strip() in ("03", "04"):
            return True
    return False


# ---------------------------------------------------------------------------
# Shared internals
# ---------------------------------------------------------------------------

def _cancel(screen, notes: str, *, pf9: bool = True) -> dict:
    if pf9:
        send_pf(screen, 9)
    return {"status": "CANCELLED.", "notes": notes, "drafts_created": 0}


def _select_ind_seq_no(screen, claim_row: dict, patient_name: str, patient_dob: str = "") -> bool:
    """
    Mirrors the Screen_220 IndSeqNo-selection block shared by
    UB_Scratch_Split (name-only matching — `patient_dob` left "") and
    UB_Scratch_NotOnline (name+dob matching — both must match): by
    newborn-type (IN/SP + sex F), by an explicit NON_NEWBORN_SEQ, or by
    name(+DOB) match. Same shape as claim_split_hcfa's
    `_select_ind_seq_no` — this macro's Screen_220 block is functionally
    identical modulo the row range (9-21 here vs 9-21 there too, actually
    the same `For j = 9 To 22 Step 2`/`For j = 9 To 21 Step 2` — both
    inclusive of 9,11,...,21).
    """
    newborn_type = claim_row.get("NEWBORN_TYPE", "")
    for j in range(9, 22, 2):
        if newborn_type == "NEW BORN":
            rel = (screen.GetString(j, 34, 2) or "").strip()
            if rel in ("IN", "SP") and (screen.GetString(j, 46, 1) or "").strip() == "F":
                place_value(screen, (screen.GetString(j, 2, 2) or "").strip(), 2, 6)
                return True
        elif newborn_type == "NON-NEW BORN":
            seq = claim_row.get("NON_NEWBORN_SEQ", "")
            if seq:
                place_value(screen, f"{int(seq):02d}", 2, 6)
                return True
            return False
        else:
            row_seq = (screen.GetString(j, 2, 2) or "").strip()
            name_match = (screen.GetString(j, 5, 11) or "").strip() in (patient_name or "")
            if patient_dob:
                if name_match and (screen.GetString(j, 37, 6) or "").strip() == patient_dob:
                    place_value(screen, row_seq, 2, 6)
                    return True
            else:
                if len(row_seq) <= 1:
                    return False
                if name_match and ((screen.GetString(j, 37, 6) or "").strip() in (patient_name or "")):
                    place_value(screen, row_seq, 2, 6)
                    return True
    return False


def _match_billing_address(screen, demographics: dict) -> None:
    """Mirrors the MatchBillingAdr loop shared by all three split routines."""
    billing_addr1 = (demographics.get("BILLING_ADDR1", "") or "").upper()
    billing_city = (demographics.get("BILLING_CITY", "") or "").upper()
    billing_state = (demographics.get("BILLING_STATE", "") or "").upper()
    billing_zip5 = (demographics.get("BILLING_ZIP", "") or "")[:5]
    billing_name = (demographics.get("BILLING_NAME", "") or "").upper()

    while True:
        matched = False
        for x in range(3, 20, 4):
            if not (screen.GetString(x, 2, 2) or "").strip():
                break
            if (
                (screen.GetString(x, 36, 30) or "").strip().upper() == billing_addr1
                and (screen.GetString(x + 1, 36, 15) or "").strip().upper() == billing_city
                and (screen.GetString(x + 1, 52, 2) or "").strip().upper() == billing_state
                and (screen.GetString(x + 1, 55, 5) or "").strip() == billing_zip5
                and (screen.GetString(x, 5, 30) or "").strip().upper() == billing_name
            ):
                place_value(screen, (screen.GetString(x, 2, 2) or "").strip(), 1, 9)
                send_enter(screen)
                matched = True
                break
        if matched:
            return
        if "COMPLETE" not in (screen.GetString(1, 2, 70) or ""):
            send_pf(screen, 8)
            continue
        send_pf(screen, 12)
        return


def _capture_460_template(screen) -> dict:
    """
    Mirrors the block of `Trim(.Getstring(...))` captures off the ORIGINAL
    claim's own BLX2460 screen (oScratch.txt:180-234 / oScratchNotOnline
    doesn't call this — it builds its template from ClaimInfo fields
    instead, see ub_scratch_not_online()). Only UB_Scratch_Split reuses the
    original draft's own screen values verbatim this way.
    """
    return {
        "POS": (screen.GetString(1, 26, 2) or "").strip(),
        "BP": (screen.GetString(2, 5, 2) or "").strip(),
        "PCN": (screen.GetString(2, 32, 18) or "").strip(),
        "TOB": (screen.GetString(2, 54, 3) or "").strip(),
        "FROM": (screen.GetString(2, 63, 6) or "").strip(),
        "THRU": (screen.GetString(2, 75, 6) or "").strip(),
        "DRG": (screen.GetString(3, 6, 5) or "").strip(),
        "ADM_HR": (screen.GetString(3, 19, 2) or "").strip(),
        "TY": (screen.GetString(3, 26, 1) or "").strip(),
        "SRC": (screen.GetString(3, 33, 1) or "").strip(),
        "DHR": (screen.GetString(3, 41, 2) or "").strip(),
        "STAT": (screen.GetString(3, 50, 2) or "").strip(),
        "MEDREC": (screen.GetString(3, 64, 16) or "").strip(),
        "OCCURCD": (screen.GetString(4, 11, 2) or "").strip(),
        "OCCURDT": (screen.GetString(4, 18, 7) or "").strip(),
        "VALUECD1": (screen.GetString(4, 35, 2) or "").strip(),
        "VALUEAMT1": (screen.GetString(4, 42, 11) or "").strip(),
        "VALUECD2": (screen.GetString(4, 63, 2) or "").strip(),
        "VALUEAMT2": (screen.GetString(4, 70, 11) or "").strip(),
        "PRV": (screen.GetString(22, 6, 1) or "").strip(),
        "MPN": (screen.GetString(22, 34, 10) or "").strip(),
        "ADM": (screen.GetString(23, 28, 7) or "").strip(),
        "E": (screen.GetString(23, 38, 9) or "").strip(),
        "CD1": (screen.GetString(25, 5, 8) or "").strip(), "CDDT1": (screen.GetString(25, 17, 6) or "").strip(),
        "CD2": (screen.GetString(25, 27, 8) or "").strip(), "CDDT2": (screen.GetString(25, 39, 6) or "").strip(),
        "CD3": (screen.GetString(25, 49, 8) or "").strip(), "CDDT3": (screen.GetString(25, 61, 6) or "").strip(),
        "CD4": (screen.GetString(26, 5, 8) or "").strip(), "CDDT4": (screen.GetString(26, 17, 6) or "").strip(),
        "CD5": (screen.GetString(26, 27, 8) or "").strip(), "CDDT5": (screen.GetString(26, 39, 6) or "").strip(),
        "CD6": (screen.GetString(26, 49, 8) or "").strip(), "CDDT6": (screen.GetString(26, 61, 6) or "").strip(),
        "PY": (screen.GetString(27, 18, 1) or "").strip(),
        "EOB": (screen.GetString(27, 24, 3) or "").strip(),
        "CHK": (screen.GetString(27, 32, 3) or "").strip(),
        "IN": (screen.GetString(27, 39, 1) or "").strip(),
        "UN": (screen.GetString(27, 44, 2) or "").strip(),
        "OP": (screen.GetString(28, 11, 5) or "").strip(),
        "FL": (screen.GetString(28, 20, 3) or "").strip(),
        "NT": (screen.GetString(28, 27, 17) or "").strip(),
    }


def _place_460_line_discount(screen, svl: dict, row: int) -> None:
    """
    Mirrors the shared "If Len(discount)>0 ... InStr '-' ..." block repeated
    in all three split routines — `svl["DISCOUNT"]` is either an
    mainframe-sourced "amt-code" pair (from get_claim_tos/get_cps_discounts)
    or a plain PDF-repricing amount (paired with INEL_CODE "908" by
    default, same as claim_split_hcfa's plain-discount path).
    """
    discount = svl.get("DISCOUNT", "")
    if discount:
        if "-" in discount:
            amt, code = discount.split("-", 1)
            place_value(screen, amt, row, 2)
            place_value(screen, code, row, 14)
        else:
            place_value(screen, discount, row, 2)
            place_value(screen, INEL_CODE, row, 14)
        place_value(screen, BYPASS_CODE, row, 30)
    else:
        place_value(screen, BYPASS_CODE, row, 14)


# ---------------------------------------------------------------------------
# UB_Scratch_Split
# ---------------------------------------------------------------------------

def ub_scratch_split(
    screen, orig_ccn: str, new_ccn: str, new_cert: str, dos_param: str,
    claim_row: dict, demographics: dict, service_lines: list[dict], settings: dict,
) -> dict:
    """Mirrors UB_Scratch_Split VBA."""
    two_lines_only = settings.get("two_lines_per_draft", "N") == "Y"
    grouping = settings.get("split_grouping", "BY DATE OF SERVICE")
    newborn_type = claim_row.get("NEWBORN_TYPE", "")

    insured_id = demographics.get("INSURED_A_UNIQUE_ID", "")
    dx_admit = demographics.get("DX_ADMIT_69", "")
    dx_primary = demographics.get("DX_PRIMARY", "")  # VBA's "Box70A_Pri_Dx" — actually Box67 (EW), see pdf_extract.py
    dx67 = [demographics.get(f"DX_67{l}", "") for l in "ABCDEFGHI"]

    date_from = _mmddyy(demographics.get("PERIOD_COV_FROM", ""))
    date_thru = _mmddyy(demographics.get("PERIOD_COV_TO", ""))

    if not is_screen(screen, "CPS520.01"):
        send_pf(screen, 9)
        return _cancel(screen, "UNABLE TO REACH CPS520.01", pf9=False)

    place_value(screen, orig_ccn, 8, 15)
    send_enter(screen)
    if not is_screen(screen, "CPS500.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

    if get_claim_tos(screen, orig_ccn, service_lines) > 0:
        return _cancel(screen, "POS-TOS MISSING.")

    send_enter(screen)
    if not is_screen(screen, "CPS850.01"):
        # Mirrors the VBA's '850 Error branch — deliberately does NOT set a
        # CANCELLED status (the two status-write lines are commented out in
        # oScratch.txt), just navigates away with no reported reason.
        return _cancel(screen, "")

    patient_name_850 = (screen.GetString(13, 2, 34) or "").strip()
    send_enter(screen)
    send_pf(screen, 8)
    place_value(screen, "310", 2, 37)
    send_enter(screen)
    if not is_screen(screen, "CPS310.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

    provider_intno = (screen.GetString(12, 65, 14) or "").strip()
    provider_npi = (screen.GetString(9, 16, 14) or "").strip()
    provider_tin = (screen.GetString(12, 2, 12) or "").strip()
    send_enter(screen)
    send_pf(screen, 8)
    place_value(screen, "460", 2, 37)
    send_enter(screen)
    tmpl = _capture_460_template(screen)

    drafts_created = 0
    n_line = 0
    total_lines = len(service_lines)

    while n_line < total_lines:
        send_pf(screen, 9)
        place_value(screen, new_ccn or orig_ccn, 16, 5)
        place_value(screen, new_cert or insured_id, 9, 15)
        place_value(screen, dos_param, 12, 15)
        send_enter(screen)
        send_enter(screen)  # 215 screen

        if not _select_ind_seq_no(screen, claim_row, patient_name_850):
            return _cancel(screen, "UNABLE TO SELECT INDSEQNO")
        send_enter(screen)
        edit_msg = (screen.GetString(31, 1, 80) or "").strip()
        if edit_msg:
            return _cancel(screen, edit_msg)

        if is_screen(screen, "CPS325.01"):
            place_value(screen, provider_tin, 3, 27)
            place_value(screen, provider_npi, 3, 49)
            place_value(screen, "11001", 5, 69)
            place_value(screen, provider_intno, 7, 30)
            send_enter(screen)
        if is_screen(screen, "CPS310.01"):
            send_enter(screen)

        if (screen.GetString(1, 67, 14) or "").strip() == "BIF2002/BIF101":
            _match_billing_address(screen, demographics)

        if is_screen(screen, "CPS920.01"):
            for x in range(4, 17, 2):  # first page only
                if (screen.GetString(x, 37, 5) or "").strip() == dx_primary:
                    if _mmddyy(dos_param) != (screen.GetString(x, 47, 6) or "").strip():
                        place_value(screen, (screen.GetString(x, 4, 4) or "").strip(), 2, 18)
                        place_value(screen, "X", 29, 55)
                        send_enter(screen)
                        place_value(screen, _mmddyy(dos_param), 5, 24)  # 910 condition change screen
                        send_enter(screen)
                    break
            send_pf(screen, 8)
            place_value(screen, "850", 2, 37)
            send_enter(screen)
            place_value(screen, dx_admit or dx_primary, 23, 6)
            place_value(screen, "Y", 23, 14)
            send_enter(screen)

        while not is_screen(screen, "BLX2460.01"):
            send_pf(screen, 8)
            place_value(screen, "460", 2, 37)
            send_enter(screen)
            if not is_screen(screen, "BLX2460.01"):
                return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

        c = 3
        line_ctr = 0
        xl_pos = _svl_pos(service_lines[n_line])
        place_value(screen, xl_pos, 1, 26)
        place_value(screen, tmpl["BP"], 2, 5)
        place_value(screen, tmpl["PCN"], 2, 32)
        place_value(screen, tmpl["TOB"], 2, 54)
        place_value(screen, date_from, 2, 63)
        place_value(screen, date_thru, 2, 75)
        place_value(screen, tmpl["DRG"], 3, 6)
        place_value(screen, tmpl["ADM_HR"], 3, 19)
        place_value(screen, tmpl["TY"], 3, 26)
        place_value(screen, tmpl["SRC"], 3, 33)
        place_value(screen, tmpl["DHR"], 3, 41)
        place_value(screen, tmpl["STAT"], 3, 50)
        place_value(screen, tmpl["MEDREC"], 3, 64)
        place_value(screen, tmpl["OCCURCD"], 4, 11)
        place_value(screen, tmpl["OCCURDT"], 4, 18)
        place_value(screen, tmpl["VALUECD1"], 4, 35)
        place_value(screen, tmpl["VALUEAMT1"], 4, 42)
        place_value(screen, tmpl["VALUECD2"], 4, 63)
        place_value(screen, tmpl["VALUEAMT2"], 4, 70)
        place_value(screen, tmpl["PRV"], 22, 6)
        place_value(screen, tmpl["MPN"], 22, 34)
        place_value(screen, tmpl["ADM"], 23, 28)
        place_value(screen, tmpl["E"], 23, 38)
        for idx, val in enumerate(dx67[:8]):
            place_value(screen, val, 24, 13 + idx * 8)
        place_value(screen, tmpl["CD1"], 25, 5); place_value(screen, tmpl["CDDT1"], 25, 17)
        place_value(screen, tmpl["CD2"], 25, 27); place_value(screen, tmpl["CDDT2"], 25, 39)
        place_value(screen, tmpl["CD3"], 25, 49); place_value(screen, tmpl["CDDT3"], 25, 61)
        place_value(screen, tmpl["CD4"], 26, 5); place_value(screen, tmpl["CDDT4"], 26, 17)
        place_value(screen, tmpl["CD5"], 26, 27); place_value(screen, tmpl["CDDT5"], 26, 39)
        place_value(screen, tmpl["CD6"], 26, 49); place_value(screen, tmpl["CDDT6"], 26, 61)
        place_value(screen, tmpl["PY"], 27, 18)
        place_value(screen, tmpl["EOB"], 27, 24)
        place_value(screen, tmpl["CHK"], 27, 32)
        place_value(screen, tmpl["IN"], 27, 39)
        place_value(screen, tmpl["UN"], 27, 44)
        place_value(screen, tmpl["OP"], 28, 11)
        place_value(screen, tmpl["FL"], 28, 20)
        place_value(screen, tmpl["NT"], 28, 27)

        for row in (6, 7, 8, 9):
            if two_lines_only and line_ctr >= 2:
                break
            if xl_pos != _svl_pos(service_lines[n_line]):
                break
            svl = service_lines[n_line]
            place_value(screen, svl.get("REV_CD", ""), row, 3)
            place_value(screen, svl.get("HCPCS_CODE", ""), row, 8)
            place_value(screen, svl.get("TOS", ""), row, 14)
            serv_date = svl.get("SERV_DATE", "")
            if serv_date:
                place_value(screen, _mmddyy(serv_date), row, 17)
            elif tmpl["POS"] in ("02", "03"):  # NO SERVICE DATE IN WEBCLAIM
                svl["SERV_DATE"] = dos_param
                place_value(screen, _mmddyy(dos_param), row, 17)
            place_value(screen, svl.get("SERV_UNITS", ""), row, 32)
            place_value(screen, svl.get("TOTAL_CHARGES", ""), row, 40)
            place_value(screen, svl.get("MOD_A", ""), row, 52)
            place_value(screen, svl.get("MOD_B", ""), row, 56)
            place_value(screen, svl.get("MOD_C", ""), row, 60)
            place_value(screen, svl.get("MOD_D", ""), row, 64)
            place_value(screen, dx_admit or dx_primary, 10, c)
            _place_460_line_discount(screen, svl, row + 6)

            c += 12
            n_line += 1
            line_ctr += 1
            if n_line >= total_lines:
                break
            if service_lines[n_line].get("CLAIM_NO") != claim_row.get("CLAIM_NO"):
                break
            if grouping == "BY DATE OF SERVICE":
                svl_date = svl.get("SERV_DATE", "")
                if _mmddyy(svl_date) != _mmddyy(service_lines[n_line].get("SERV_DATE", "")):
                    break

        drafts_created += 1
        send_enter(screen)
        if is_screen(screen, "CPS445.01"):
            place_value(screen, "x", 29, 16)  # HSP
            send_enter(screen)
            place_value(screen, "x", 29, 78)  # HSP
            send_enter(screen)

        if not is_screen(screen, "CPS506.01"):
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip(), pf9=False)

        note = f"{'NEWBORN SPLIT MACRO ' if newborn_type == 'NEW BORN' else 'SPLIT MACRO '}{drafts_created}"
        place_value(screen, RLS_CODE, 3, 13)
        place_value(screen, LST_RLS, 3, 39)
        place_value(screen, PEND_RSN, 3, 53)
        place_value(screen, FLUP_DAYS, 4, 38)
        place_value(screen, PAYEE, 7, 8)
        place_value(screen, note, 4, 50)
        send_enter(screen)
        send_pf(screen, 8)
        place_value(screen, "460", 2, 37)
        send_enter(screen)

    send_pf(screen, 9)
    return {"status": "DONE.", "notes": f"DRAFTS CREATED: {drafts_created}", "drafts_created": drafts_created}


# ---------------------------------------------------------------------------
# UB_NonScratch_Split
# ---------------------------------------------------------------------------

def ub_nonscratch_split(screen, claim_row: dict, service_lines: list[dict], settings: dict) -> dict:
    """Mirrors UB_NonScratch_Split VBA."""
    ccn = claim_row.get("CLAIM_NO", "")
    two_lines_only = settings.get("two_lines_per_draft", "N") == "Y"
    grouping = settings.get("split_grouping", "BY DATE OF SERVICE")
    date_from = _mmddyy(claim_row.get("PERIOD_COV_FROM", ""))
    date_thru = _mmddyy(claim_row.get("PERIOD_COV_TO", ""))
    # Mirrors `Select Case MN.Range("AA2")` — a single run-level dropdown on
    # the MAIN sheet (not a per-claim field), so this comes from `settings`.
    inel_remove_mode = settings.get("inel_remove_mode", "")

    if not is_screen(screen, "CPS520.01"):
        send_pf(screen, 9)
        return _cancel(screen, "UNABLE TO REACH CPS520.01", pf9=False)
    place_value(screen, ccn, 8, 15)
    send_enter(screen)

    if not is_screen(screen, "CPS500.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

    if settings.get("get_cps_discount", "N") == "Y":
        get_cps_discounts(screen, ccn, service_lines)
    send_enter(screen)

    if not is_screen(screen, "CPS850.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())
    send_enter(screen)

    while not is_screen(screen, "BLX2460.01"):
        if is_screen(screen, "CPS450.01"):
            send_pf(screen, 8)
            place_value(screen, "460", 2, 37)
            send_enter(screen)
            continue
        return _cancel(screen, "Not Found: Hospital Service Add Screen")

    pos_460 = (screen.GetString(1, 26, 2) or "").strip()
    place_value(screen, date_from, 2, 63)
    place_value(screen, date_thru, 2, 75)

    if inel_remove_mode in ("REMOVE ALL EXISTING INEL", "REMOVE EXISTING INEL1"):
        remove_value(screen, 12, 2); remove_value(screen, 12, 14)
        remove_value(screen, 13, 2); remove_value(screen, 13, 14)
        remove_value(screen, 14, 2); remove_value(screen, 14, 14)
        remove_value(screen, 15, 2); remove_value(screen, 15, 14)
    if inel_remove_mode in ("REMOVE ALL EXISTING INEL", "REMOVE EXISTING INEL2"):
        remove_value(screen, 12, 18); remove_value(screen, 12, 30)
        remove_value(screen, 13, 18); remove_value(screen, 13, 30)
        remove_value(screen, 14, 18); remove_value(screen, 14, 30)
        remove_value(screen, 15, 18); remove_value(screen, 15, 30)

    place_value(screen, BYPASS_CODE, 12, 14)
    place_value(screen, BYPASS_CODE, 13, 14)
    place_value(screen, BYPASS_CODE, 14, 14)
    place_value(screen, BYPASS_CODE, 15, 14)
    send_enter(screen)

    if is_screen(screen, "CPS445.01"):
        send_enter(screen)
        send_pf(screen, 8)
        place_value(screen, "460", 2, 37)
        send_enter(screen)
        place_value(screen, "x", 29, 78)  # DPSV
        send_enter(screen)

    if not is_screen(screen, "CPS506.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

    place_value(screen, RLS_CODE, 3, 13)
    place_value(screen, LST_RLS, 3, 39)
    place_value(screen, PEND_RSN, 3, 53)
    place_value(screen, FLUP_DAYS, 4, 38)
    place_value(screen, PAYEE, 7, 8)
    place_value(screen, "Old Line", 4, 50)
    send_enter(screen)

    if not is_screen(screen, "CPS520.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())
    send_pf(screen, 8)
    place_value(screen, "460", 2, 37)
    send_enter(screen)

    n_line = 0
    total_lines = len(service_lines)
    drafts_created = 0

    while n_line < total_lines:
        line_ctr = 0
        c = 3
        place_value(screen, pos_460, 1, 26)
        place_value(screen, date_from, 2, 63)
        place_value(screen, date_thru, 2, 75)

        group_date = service_lines[n_line].get("SERV_DATE", "")
        for row in (6, 7, 8, 9):
            if two_lines_only and line_ctr >= 2:
                break
            if n_line >= total_lines:
                break
            svl = service_lines[n_line]
            place_value(screen, svl.get("REV_CD", ""), row, 3)
            place_value(screen, svl.get("HCPCS_CODE", ""), row, 8)
            place_value(screen, svl.get("TOS", ""), row, 14)
            place_value(screen, _mmddyy(svl.get("SERV_DATE", "")), row, 17)
            place_value(screen, svl.get("SERV_UNITS", ""), row, 32)
            place_value(screen, svl.get("TOTAL_CHARGES", ""), row, 40)
            place_value(screen, svl.get("MOD_A", ""), row, 52)
            place_value(screen, svl.get("MOD_B", ""), row, 56)
            place_value(screen, svl.get("MOD_C", ""), row, 60)
            place_value(screen, svl.get("MOD_D", ""), row, 64)
            place_value(screen, (screen.GetString(24, 5, 7) or "").strip(), 10, c)
            _place_460_line_discount(screen, svl, row + 6)

            c += 12
            n_line += 1
            line_ctr += 1
            if n_line >= total_lines:
                break
            if grouping == "BY DATE OF SERVICE":
                if _mmddyy(group_date) != _mmddyy(service_lines[n_line].get("SERV_DATE", "")):
                    break
            if service_lines[n_line].get("CLAIM_NO") != ccn:
                break

        drafts_created += 1
        send_enter(screen)
        if is_screen(screen, "CPS445.01"):
            place_value(screen, "x", 29, 16)
            send_enter(screen)
            place_value(screen, "x", 29, 78)
            send_enter(screen)

        if is_screen(screen, "CPS506.01"):
            place_value(screen, RLS_CODE, 3, 13)
            place_value(screen, LST_RLS, 3, 39)
            place_value(screen, PEND_RSN, 3, 53)
            place_value(screen, FLUP_DAYS, 4, 38)
            place_value(screen, PAYEE, 7, 8)
            place_value(screen, f"Split Macro {drafts_created}", 4, 50)
            send_enter(screen)
            send_pf(screen, 8)
            place_value(screen, "460", 2, 37)
            send_enter(screen)
        else:
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip(), pf9=False)

    send_pf(screen, 9)
    return {"status": "DONE.", "notes": f"DRAFTS CREATED: {drafts_created}", "drafts_created": drafts_created}


# ---------------------------------------------------------------------------
# UB_Scratch_NotOnline
# ---------------------------------------------------------------------------

def ub_scratch_not_online(
    screen, orig_ccn: str, new_ccn: str, new_cert: str, dos_param: str,
    claim_row: dict, demographics: dict, service_lines: list[dict], settings: dict,
) -> dict:
    """Mirrors UB_Scratch_NotOnline VBA ('Added 2023.08.11)."""
    two_lines_only = settings.get("two_lines_per_draft", "N") == "Y"
    newborn_type = claim_row.get("NEWBORN_TYPE", "")

    date_from = _mmddyy(demographics.get("PERIOD_COV_FROM", ""))
    date_thru = _mmddyy(demographics.get("PERIOD_COV_TO", ""))
    tob = demographics.get("TYPE_OF_BILL", "")
    adm_hr = (demographics.get("ADMISSION_HR", "") or "")[:2]
    adm_ty = demographics.get("ADMISSION_TYPE", "")
    adm_src = demographics.get("ADMISSION_SRC", "")
    dhr = (demographics.get("DHR", "") or "")[:2]
    stat = demographics.get("STAT", "")
    med_rec = demographics.get("MED_REC_NO", "")
    insured_id = demographics.get("INSURED_A_UNIQUE_ID", "")
    dx_admit = demographics.get("DX_ADMIT_69", "")
    dx_primary = demographics.get("DX_PRIMARY", "")  # VBA's "Box70A_Pri_Dx" — actually Box67 (EW), see pdf_extract.py
    dx67 = [demographics.get(f"DX_67{l}", "") for l in "ABCDEFGHI"]

    fed_tax_no = demographics.get("FED_TAX_ID", "")
    npi_56 = demographics.get("NPI_56", "")
    billing_state = demographics.get("BILLING_STATE", "")
    billing_zip5 = (demographics.get("BILLING_ZIP", "") or "")[:5]
    pps_cd = f"{demographics.get('PPS_CODE_71', '') or '':>05}"
    principal_cd = demographics.get("PRINCIPAL_PROC_CODE_74", "")
    occ_a_code = demographics.get("OCC_A_31_CODE", "")
    occ_a_date_raw = demographics.get("OCC_A_31_DATE", "")
    occ_a_date = _mmddyy(occ_a_date_raw) if len(occ_a_date_raw or "") > 1 else ""
    value_39a_code = demographics.get("VALUE_39A_CODE", "")
    value_39a_amt = demographics.get("VALUE_39A_AMT", "")
    value_40a_code = demographics.get("VALUE_40A_CODE", "")
    value_40a_amt = demographics.get("VALUE_40A_AMT", "")
    principal_dt_raw = demographics.get("PRINCIPAL_PROC_DATE_74", "")
    principal_dt = _mmddyy(principal_dt_raw) if len(principal_dt_raw or "") > 1 else ""

    if not is_screen(screen, "CPS520.01"):
        send_pf(screen, 9)
        return _cancel(screen, "UNABLE TO REACH CPS520.01", pf9=False)

    place_value(screen, orig_ccn, 8, 15)
    place_value(screen, insured_id, 9, 15)
    place_value(screen, orig_ccn, 16, 5)
    place_value(screen, date_from, 12, 15)
    send_enter(screen)

    if not is_screen(screen, "CPS215.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())
    send_enter(screen)

    if not is_screen(screen, "CPS220.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())
    patient_dob = _mmddyy(demographics.get("PATIENT_DOB", ""))
    if not _select_ind_seq_no(screen, claim_row, demographics.get("PATIENT_NAME", ""), patient_dob):
        return _cancel(screen, "UNABLE TO SELECT INDSEQNO")
    send_enter(screen)

    if is_screen(screen, "CPS325.01"):
        place_value(screen, fed_tax_no, 3, 27)
        place_value(screen, npi_56, 3, 49)
        place_value(screen, billing_state, 5, 61)
        place_value(screen, billing_zip5, 5, 69)
        place_value(screen, demographics.get("BOX_HP_UNPOPULATED", ""), 7, 30)  # see pdf_extract.py module docstring
        send_enter(screen)

    fpg = 1
    while is_screen(screen, "CPS320.01"):
        if fpg > 5:
            return _cancel(screen, "MULTIPLE PROVIDER")
        matched = False
        for x in range(8, 19):
            if not (screen.GetString(x, 5, 31) or "").strip():
                break
            if billing_zip5 == (screen.GetString(x, 46, 5) or "").strip() and (screen.GetString(x, 37, 3) or "").strip() == "HSP":
                place_value(screen, (screen.GetString(x, 2, 2) or "").strip(), 3, 52)
                matched = True
                break
        if matched:
            send_enter(screen)
            break
        if "MORE DATA:" in (screen.GetString(28, 2, 70) or ""):
            send_pf(screen, 11)
            fpg += 1
            continue
        return _cancel(screen, "MULTIPLE PROVIDER")

    if not is_screen(screen, "CPS310.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())
    send_enter(screen)

    if (screen.GetString(1, 67, 14) or "").strip() == "BIF2002/BIF101":
        _match_billing_address(screen, demographics)

    if is_screen(screen, "CPS920.01"):
        if newborn_type == "NEW BORN" and not find_03_04_tod(screen):
            return _cancel(screen, "TOD 03 OR 04 NOT FOUND")
        send_pf(screen, 8)
        place_value(screen, "850", 2, 37)
        send_enter(screen)
        place_value(screen, dx_primary, 23, 6)
        place_value(screen, "Y", 23, 14)
        send_enter(screen)

    while not is_screen(screen, "BLX2460.01"):
        send_pf(screen, 8)
        place_value(screen, "460", 2, 37)
        send_enter(screen)
        if not is_screen(screen, "BLX2460.01"):
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

    n_line = 0
    total_lines = len(service_lines)
    drafts_created = 0
    pos_460 = ""

    while n_line < total_lines:
        c = 3
        line_ctr = 0
        place_value(screen, tob, 2, 54)
        place_value(screen, date_from, 2, 63)
        place_value(screen, date_thru, 2, 75)
        place_value(screen, pps_cd, 3, 6)
        place_value(screen, adm_hr, 3, 19)
        place_value(screen, adm_ty, 3, 26)
        place_value(screen, adm_src, 3, 33)
        place_value(screen, dhr, 3, 41)
        place_value(screen, stat, 3, 50)
        place_value(screen, med_rec, 3, 64)
        place_value(screen, occ_a_code, 4, 11)
        place_value(screen, occ_a_date, 4, 18)
        place_value(screen, value_39a_code, 4, 35)
        place_value(screen, value_39a_amt, 4, 42)
        place_value(screen, value_40a_code, 4, 63)
        place_value(screen, value_40a_amt, 4, 70)
        # DEFAULT TO "00000000" AS DISCUSSED 2023.08.11
        place_value(screen, "00000000", 25, 5)
        place_value(screen, principal_dt if principal_dt else date_from, 25, 17)

        for row in (6, 7, 8, 9):
            if two_lines_only and line_ctr >= 2:
                break
            if n_line >= total_lines:
                break
            svl = service_lines[n_line]
            place_value(screen, svl.get("REV_CD", ""), row, 3)
            place_value(screen, svl.get("HCPCS_CODE", ""), row, 8)
            serv_date = svl.get("SERV_DATE", "")
            if serv_date:
                place_value(screen, _mmddyy(serv_date), row, 17)
            elif pos_460 in ("02", "03"):
                svl["SERV_DATE"] = dos_param
                place_value(screen, _mmddyy(dos_param), row, 17)
            place_value(screen, svl.get("SERV_UNITS", ""), row, 32)
            place_value(screen, svl.get("TOTAL_CHARGES", ""), row, 40)
            place_value(screen, svl.get("MOD_A", ""), row, 52)
            place_value(screen, svl.get("MOD_B", ""), row, 56)
            place_value(screen, svl.get("MOD_C", ""), row, 60)
            place_value(screen, svl.get("MOD_D", ""), row, 64)
            place_value(screen, dx_admit or dx_primary, 10, c)
            _place_460_line_discount(screen, svl, row + 6)

            c += 10  # NOTE: +10 here, not +12 — matches oScratchNotOnline literally (differs from the other two subs)
            n_line += 1
            line_ctr += 1
            if n_line >= total_lines:
                break
            if service_lines[n_line].get("CLAIM_NO") != claim_row.get("CLAIM_NO"):
                break

        drafts_created += 1
        send_enter(screen)

        while is_screen(screen, "BLX2460.01"):
            if "PRE-CERT" in (screen.GetString(31, 2, 80) or ""):
                place_value(screen, "RP", 2, 5)
                send_enter(screen)
                continue
            break

        if is_screen(screen, "CPS445.01"):
            place_value(screen, "x", 29, 16)
            send_enter(screen)
            place_value(screen, "x", 29, 78)
            send_enter(screen)

        if not is_screen(screen, "CPS506.01"):
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip(), pf9=False)

        note = f"{'NEWBORN SPLIT UNDER MOM ' if newborn_type == 'NEW BORN' else 'SPLIT MACRO '}{drafts_created}"
        place_value(screen, RLS_CODE, 3, 13)
        place_value(screen, LST_RLS, 3, 39)
        place_value(screen, PEND_RSN, 3, 53)
        place_value(screen, FLUP_DAYS, 4, 38)
        place_value(screen, PAYEE, 7, 8)
        place_value(screen, note, 4, 50)
        send_enter(screen)
        send_pf(screen, 8)
        place_value(screen, "460", 2, 37)
        send_enter(screen)

    send_pf(screen, 9)
    return {"status": "DONE.", "notes": f"DRAFTS CREATED: {drafts_created}", "drafts_created": drafts_created}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _svl_pos(svl: dict) -> str:
    """The POS a service line belongs to, once get_claim_tos() has populated it."""
    return svl.get("POS", "")


def _mmddyy(val: str) -> str:
    """
    Best-effort port of VBA `Format(x, "MMDDYY")`. Handles the shapes this
    module actually passes through it: "MM/DD/YY" or "MM/DD/YYYY" (from
    pdf_extract's date fields, normalized with "/" separators) and already-
    6-digit "MMDDYY" (left as-is). Returns "" for blank input rather than
    raising — several call sites pass a possibly-empty field straight
    through, same as PLACEVALUE's own no-op-on-blank guard downstream.
    """
    val = (val or "").strip()
    if not val:
        return ""
    if "/" in val:
        parts = val.split("/")
        if len(parts) == 3:
            mm, dd, yy = parts
            yy = yy[-2:] if len(yy) > 2 else yy
            return f"{mm.zfill(2)}{dd.zfill(2)}{yy.zfill(2)}"
    digits = "".join(ch for ch in val if ch.isdigit())
    if len(digits) == 6:
        return digits
    return val
