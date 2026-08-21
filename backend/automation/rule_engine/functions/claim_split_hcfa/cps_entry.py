"""
Claim Split HCFA — PART 2: keying split drafts into the CPS mainframe.

Ports oScratch.txt, oNonScratch.txt and oScratchNotOnline. This is the
"typing into the terminal" half of the macro — nothing here talks to the
web; the claim data it types was already fetched and parsed by
web_claims.py / pdf_extract.py (PART 1) before any of these functions run.

Each of the three split routines below is a straight port of its VBA
namesake and returns a small status dict — `{"status": "DONE."/"CANCELLED.",
"notes": "...", "drafts_created": n}` — instead of writing MAIN columns A/B.

Shared shape used throughout:
  claim_row      dict  — MAIN claim-block fields (CLAIM_NO, NEW_CERT,
                          NEW_CCN, NEW_DOS, NON_NEWBORN_SEQ, NEWBORN_TYPE)
  demographics   dict  — from pdf_extract.extract_demographics()
  service_lines  list[dict] — from pdf_extract.extract_service_lines(),
                          already repriced + DX-resolved by extract_claim()
  settings       dict  — the run-level options (mirrors the checkboxes/
                          dropdowns on the VBA MAIN sheet): apply_uc,
                          two_lines_per_draft, get_cps_discount, bypass,
                          split_grouping ("BY DATE OF SERVICE"/"BY DIAGNOSIS")
"""

from __future__ import annotations

from .utils import is_screen, place_value, send_enter, send_pf

BYPASS_CODE = "001"
INEL_CODE = "908"
RLS_CODE = "60"
LST_RLS = "N"
PEND_RSN = "o99"
FLUP_DAYS = "001"
PAYEE = "0"


# ---------------------------------------------------------------------------
# GetClaim_Inel_OI — reads existing inel/OI/BN data off the ORIGINAL claim
# ---------------------------------------------------------------------------

def get_claim_inel_oi(screen, ccn: str, service_lines: list[dict]) -> None:
    """
    Mirrors GetClaim_Inel_OI VBA. Walks every draft of the currently-open
    claim on screen, and for each populated service line matches it against
    `service_lines` by (begin date, CPT, DX) — mirroring the VBA's Excel
    AutoFilter on those three columns — setting INEL_OI_BUNDLE to the
    pipe-delimited bundle hcfa_scratch_split() expects:
        "INEL_AMT1-INEL_CD1|INEL_AMT2-INEL_CD2|OI_ELIG-OI_PAID-OI-BN-BN_AMT-SP-NDC"
    """
    while True:
        for r in range(6, 19, 2):
            ln = (screen.GetString(r, 2, 2) or "").strip()
            if not ln:
                break
            place_value(screen, ln, 3, 26)
            send_enter(screen)
            send_enter(screen)

            k = 9
            for i in range(5, 12, 2):
                if (screen.GetString(i, 4, 6) or "").strip():
                    bgn = f"{(screen.GetString(i, 4, 2) or '').strip()}/{(screen.GetString(i, 6, 2) or '').strip()}/{(screen.GetString(i, 8, 2) or '').strip()}"
                    cpt = (screen.GetString(i, 41, 5) or "").strip()
                    dx = (screen.GetString(i + 1, 70, 7) or "").strip()
                    bundle = (
                        f"{(screen.GetString(i + k, 2, 11) or '').strip()}-{(screen.GetString(i + k, 14, 3) or '').strip()}|"
                        f"{(screen.GetString(i + k, 18, 11) or '').strip()}-{(screen.GetString(i + k, 30, 3) or '').strip()}|"
                        f"{(screen.GetString(i + k + 6, 4, 11) or '').strip()}-{(screen.GetString(i + k + 6, 16, 11) or '').strip()}-"
                        f"{(screen.GetString(i + k + 6, 28, 1) or '').strip()}-{(screen.GetString(i + k + 6, 31, 1) or '').strip()}-"
                        f"{(screen.GetString(i + k + 6, 36, 11) or '').strip()}-{(screen.GetString(i + k + 6, 48, 5) or '').strip()}-"
                        f"{(screen.GetString(i + k + 6, 56, 11) or '').strip()}"
                    )
                    for svl in service_lines:
                        if (
                            svl.get("CLAIM_NO") == ccn
                            and svl.get("DOS_FROM") == bgn
                            and svl.get("CPT_HCPCS") == cpt
                            and svl.get("DX_CODE", "")[:7] == dx
                        ):
                            svl["INEL_OI_BUNDLE"] = bundle
                k -= 1

            send_pf(screen, 9)
            place_value(screen, ccn, 8, 15)
            send_enter(screen)
        if "MORE DATA" not in (screen.GetString(20, 2, 60) or "").upper():
            break
        send_pf(screen, 11)


def get_cps_discounts(screen, ccn: str, service_lines: list[dict]) -> None:
    """
    Mirrors GetCPS_Discounts VBA (used by Non-Scratch mode when the "Get CPS
    Discount" option is on). Same navigation as get_claim_inel_oi(), but only
    captures a plain "amt-code" pair into CPS_DISCOUNT instead of the full
    inel/OI/BN bundle.
    """
    while True:
        for r in range(6, 19, 2):
            ln = (screen.GetString(r, 2, 2) or "").strip()
            if not ln:
                break
            place_value(screen, ln, 3, 26)
            send_enter(screen)
            send_enter(screen)

            k = 9
            for i in range(5, 12, 2):
                if (screen.GetString(i, 4, 6) or "").strip():
                    bgn = f"{(screen.GetString(i, 4, 2) or '').strip()}/{(screen.GetString(i, 6, 2) or '').strip()}/{(screen.GetString(i, 8, 2) or '').strip()}"
                    cpt = (screen.GetString(i, 41, 5) or "").strip()
                    dx = (screen.GetString(i + 1, 70, 6) or "").strip()
                    amt = (screen.GetString(i + k, 2, 11) or "").strip() or "0.00"
                    code = (screen.GetString(i + k, 14, 3) or "").strip() or "001"
                    for svl in service_lines:
                        if (
                            svl.get("CLAIM_NO") == ccn
                            and svl.get("DOS_FROM") == bgn
                            and svl.get("CPT_HCPCS") == cpt
                            and svl.get("DX_CODE", "")[:6] == dx
                        ):
                            svl["CPS_DISCOUNT"] = f"{amt}-{code}"
                k -= 1

            send_pf(screen, 9)
            place_value(screen, ccn, 8, 15)
            send_enter(screen)
        if "MORE DATA" not in (screen.GetString(20, 2, 60) or "").upper():
            break
        send_pf(screen, 11)


def find_03_04_tod(screen) -> bool:
    """Mirrors Find_03_04_TOD VBA — True if any condition on the (first) page has TOD 03 or 04."""
    for i in range(4, 19, 2):
        if not (screen.GetString(i, 4, 4) or "").strip():
            break
        if (screen.GetString(i, 34, 2) or "").strip() in ("03", "04"):
            return True
    return False


def hcfa_pos_collection(pos_reference_rows: list[tuple[str, str]]) -> dict:
    """
    Mirrors HCFA_POS_Collection VBA. `pos_reference_rows` is the REFERENCE
    sheet's (HCA POS, CPS POS) pairs, loaded by script.py from wherever that
    static lookup now lives (a CSV, most likely — see script.py). Only used
    by hcfa_scratch_not_online().
    """
    out: dict[str, str] = {}
    for hca_pos, cps_pos in pos_reference_rows:
        hca_pos = (hca_pos or "").strip()
        if hca_pos and hca_pos not in out:
            out[hca_pos] = (cps_pos or "").strip()
    return out


def _service_line_charge_for_split(svl: dict, settings: dict) -> tuple[str, str]:
    """
    Returns the (amount, code) to key as Inel Amt1/Cd1 on a single line for
    Non-Scratch / Scratch-Not-Online mode, from CPS_DISCOUNT ("amt-code",
    set by get_cps_discounts) if present, else DISCOUNT_INELIGIBLE (the
    plain PDF-repricing amount, always paired with INEL_CODE) — mirrors the
    `If InStr(..., "-") > 0` branch in HCFA_NonScratch_Split.
    """
    cps_discount = svl.get("CPS_DISCOUNT", "")
    if cps_discount and "-" in cps_discount:
        amt, code = cps_discount.split("-", 1)
        return amt, code
    disc = svl.get("DISCOUNT_INELIGIBLE", "")
    if disc:
        return disc, INEL_CODE
    return "", ""


# ---------------------------------------------------------------------------
# HCFA_Scratch_Split
# ---------------------------------------------------------------------------

def hcfa_scratch_split(
    screen, orig_ccn: str, new_ccn: str, new_cert: str, dos_param: str,
    claim_row: dict, demographics: dict, service_lines: list[dict], settings: dict,
) -> dict:
    """Mirrors HCFA_Scratch_Split VBA."""
    two_lines_only = settings.get("two_lines_per_draft", "N") == "Y"
    bypass_on = settings.get("bypass", "N") == "Y"
    grouping = settings.get("split_grouping", "BY DATE OF SERVICE")
    newborn_type = claim_row.get("NEWBORN_TYPE", "")

    insured_id = demographics.get("INSURED_ID", "")
    dx1 = demographics.get("DX_A", "")

    if not is_screen(screen, "CPS520.01"):
        place_value(screen, orig_ccn, 8, 15)
        send_enter(screen)
        if not is_screen(screen, "CPS500.01"):
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

        get_claim_inel_oi(screen, orig_ccn, service_lines)
        send_enter(screen)
        if not is_screen(screen, "CPS850.01"):
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

        patient_name_850 = (screen.GetString(13, 2, 34) or "").strip()
        mbr_id_850 = (screen.GetString(3, 50, 8) or "").strip()
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
        place_value(screen, "450", 2, 37)
        send_enter(screen)
        pos_450 = (screen.GetString(2, 6, 2) or "").strip()
        dx2_450 = (screen.GetString(2, 36, 7) or "").strip()
        dx3_450 = (screen.GetString(2, 49, 7) or "").strip()
        prv_450 = (screen.GetString(26, 9, 1) or "").strip()
        act_450 = (screen.GetString(27, 26, 18) or "").strip()

        total_lines = len(service_lines)
        n_line = 0  # 0-based index into service_lines of the next unplaced line
        drafts_created = 0

        while n_line < total_lines:
            send_pf(screen, 9)
            place_value(screen, new_cert or insured_id, 9, 15)

            while True:
                place_value(screen, new_ccn or orig_ccn, 16, 5)
                place_value(screen, dos_param, 12, 15)
                send_enter(screen)
                if is_screen(screen, "CPS125.01"):
                    send_pf(screen, 9)
                    place_value(screen, mbr_id_850, 9, 15)
                    continue
                break

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
                send_pf(screen, 8)
                place_value(screen, "850", 2, 37)
                send_enter(screen)
                place_value(screen, dx1, 23, 6)
                place_value(screen, "Y", 23, 14)
                send_enter(screen)

            if not is_screen(screen, "CPS450.01"):
                return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

            place_value(screen, pos_450, 2, 6)
            place_value(screen, dx2_450, 2, 36)
            place_value(screen, dx3_450, 2, 49)
            place_value(screen, prv_450, 26, 9)
            place_value(screen, act_450, 27, 26)

            n_line = _key_hcfa_service_lines(
                screen, service_lines, n_line, total_lines, grouping, two_lines_only,
                bypass_on=bypass_on, use_inel_oi_bundle=True,
            )

            send_enter(screen)
            if is_screen(screen, "CPS445.01"):
                send_enter(screen)
                place_value(screen, "x", 29, 76)
                send_enter(screen)

            if not is_screen(screen, "CPS506.01"):
                return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

            note = f"{'NEWBORN SPLIT MACRO ' if newborn_type == 'NEW BORN' else 'SPLIT MACRO '}{drafts_created + 1}"
            place_value(screen, RLS_CODE, 3, 13)
            place_value(screen, LST_RLS, 3, 39)
            place_value(screen, PEND_RSN, 3, 53)
            place_value(screen, FLUP_DAYS, 4, 38)
            place_value(screen, PAYEE, 7, 8)
            place_value(screen, note, 4, 50)
            send_enter(screen)
            drafts_created += 1

        send_pf(screen, 9)
        return {"status": "DONE.", "notes": f"DRAFTS CREATED: {drafts_created}", "drafts_created": drafts_created}

    send_pf(screen, 9)
    return _cancel(screen, "UNABLE TO REACH CPS520.01")


# ---------------------------------------------------------------------------
# HCFA_NonScratch_Split
# ---------------------------------------------------------------------------

def hcfa_nonscratch_split(screen, claim_row: dict, service_lines: list[dict], settings: dict) -> dict:
    """Mirrors HCFA_NonScratch_Split VBA."""
    ccn = claim_row.get("CLAIM_NO", "")
    two_lines_only = settings.get("two_lines_per_draft", "N") == "Y"
    grouping = settings.get("split_grouping", "BY DATE OF SERVICE")

    if not is_screen(screen, "CPS520.01"):
        return _cancel(screen, "UNABLE TO REACH CPS520.01")
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

    while not is_screen(screen, "CPS450.01"):
        if is_screen(screen, "BLX2460.01"):
            send_pf(screen, 8)
            place_value(screen, "450", 2, 37)
            send_enter(screen)
            continue
        return _cancel(screen, "Not Found: HCFA Service Add Screen")

    screen_pos = (screen.GetString(2, 6, 2) or "").strip()
    place_value(screen, BYPASS_CODE, 14, 14)
    place_value(screen, BYPASS_CODE, 15, 14)
    place_value(screen, BYPASS_CODE, 16, 14)
    place_value(screen, BYPASS_CODE, 17, 14)
    send_enter(screen)
    _resolve_cond_onset_and_past_term_edits(screen)

    if is_screen(screen, "CPS445.01"):
        send_enter(screen)
        send_pf(screen, 8)
        place_value(screen, "450", 2, 37)
        send_enter(screen)
        place_value(screen, "x", 29, 76)
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
    place_value(screen, "450", 2, 37)
    send_enter(screen)

    n_line = 0
    total_lines = len(service_lines)
    drafts_created = 0

    while n_line < total_lines:
        place_value(screen, screen_pos, 2, 6)
        n_line = _key_hcfa_service_lines(
            screen, service_lines, n_line, total_lines, grouping, two_lines_only,
            bypass_on=False, use_inel_oi_bundle=False,
        )
        drafts_created += 1
        send_enter(screen)
        if is_screen(screen, "CPS445.01"):
            send_enter(screen)
            place_value(screen, "x", 29, 76)
            send_enter(screen)

        if is_screen(screen, "CPS506.01"):
            place_value(screen, RLS_CODE, 3, 13)
            place_value(screen, LST_RLS, 3, 39)
            place_value(screen, PEND_RSN, 3, 53)
            place_value(screen, FLUP_DAYS, 4, 38)
            place_value(screen, PAYEE, 7, 8)
            place_value(screen, f"Split Macro {drafts_created}", 4, 50)
            send_enter(screen)
            if is_screen(screen, "CPS506.01"):
                return _cancel(screen, f"DRAFTS CREATED: {drafts_created} — "
                                        f"{(screen.GetString(31, 1, 80) or '').strip()} {(screen.GetString(32, 1, 80) or '').strip()}")
            send_pf(screen, 8)
            place_value(screen, "450", 2, 37)
            send_enter(screen)
        elif is_screen(screen, "CPS450.01"):
            _resolve_cond_onset_and_past_term_edits(screen)
        else:
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

    send_pf(screen, 9)
    return {"status": "DONE.", "notes": f"DRAFTS CREATED: {drafts_created}", "drafts_created": drafts_created}


# ---------------------------------------------------------------------------
# HCFA_Scratch_NotOnline
# ---------------------------------------------------------------------------

def hcfa_scratch_not_online(
    screen, orig_ccn: str, new_ccn: str, new_cert: str, dos_param: str,
    claim_row: dict, demographics: dict, service_lines: list[dict],
    pos_reference: dict, settings: dict,
) -> dict:
    """Mirrors HCFA_Scratch_NotOnline VBA."""
    two_lines_only = settings.get("two_lines_per_draft", "N") == "Y"
    grouping = settings.get("split_grouping", "BY DATE OF SERVICE")
    newborn_type = claim_row.get("NEWBORN_TYPE", "")

    insured_id = demographics.get("INSURED_ID", "")
    dx1 = demographics.get("DX_A", "")
    fed_tax_no = demographics.get("FED_TAX_ID", "")
    supplier_name = demographics.get("BOX31_SUPPLIER", "")
    service_fac_state = demographics.get("SERVICE_FAC_STATE", "")
    service_fac_zip = (demographics.get("SERVICE_FAC_ZIP", "") or "")[:5]

    if not is_screen(screen, "CPS520.01"):
        send_pf(screen, 9)
        return _cancel(screen, "UNABLE TO REACH CPS520.01")

    place_value(screen, orig_ccn, 8, 15)
    place_value(screen, insured_id, 9, 15)
    place_value(screen, orig_ccn, 16, 5)
    place_value(screen, dos_param, 12, 15)
    send_enter(screen)

    if not is_screen(screen, "CPS215.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())
    send_enter(screen)

    if not is_screen(screen, "CPS220.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())
    if not _select_ind_seq_no(screen, claim_row, demographics.get("PATIENT_NAME", ""), demographics.get("PATIENT_DOB", "")):
        return _cancel(screen, "UNABLE TO SELECT INDSEQNO")
    send_enter(screen)

    if is_screen(screen, "CPS325.01"):
        place_value(screen, fed_tax_no, 3, 27)
        name_no_comma = supplier_name.split(",")[0].strip() if "," in supplier_name else supplier_name[:3]
        place_value(screen, name_no_comma, 5, 18)
        place_value(screen, service_fac_state, 5, 61)
        place_value(screen, service_fac_zip, 5, 69)
        # Mirrors `PLACEVALUE Trim(INF.Range("BP" & a)), 7, 30` — ClaimInfo
        # column BP is never populated by any extraction routine in the VBA
        # either (flagged in IO_Reference.html), so this is a documented
        # no-op today, not a gap introduced by this port.
        place_value(screen, demographics.get("BOX_BP_UNPOPULATED", ""), 7, 30)
        send_enter(screen)

    if is_screen(screen, "CPS320.01"):
        matched = False
        first_word, last_word = _split_supplier_name(supplier_name)
        for page in range(5):
            for x in range(8, 19):
                entry = (screen.GetString(x, 5, 31) or "").strip()
                if not entry:
                    break
                if first_word in entry and last_word in entry:
                    place_value(screen, (screen.GetString(x, 2, 2) or "").strip(), 3, 52)
                    matched = True
                    break
            if matched:
                break
            if "MORE DATA:" in (screen.GetString(28, 2, 70) or ""):
                send_pf(screen, 11)
                continue
            break
        if not matched:
            return _cancel(screen, "MULTIPLE PROVIDER")
        send_enter(screen)

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
        place_value(screen, dx1, 23, 6)
        place_value(screen, "Y", 23, 14)
        send_enter(screen)

    if not is_screen(screen, "CPS450.01"):
        return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

    n_line = 0
    total_lines = len(service_lines)
    drafts_created = 0

    while n_line < total_lines:
        if not is_screen(screen, "CPS450.01"):
            send_pf(screen, 8)
            place_value(screen, "450", 2, 37)
            send_enter(screen)
            continue

        svl_pos = service_lines[n_line].get("POS", "") if n_line < total_lines else ""
        cps_pos = pos_reference.get(svl_pos, "")
        if cps_pos:
            place_value(screen, cps_pos[:2], 2, 6)
        dx2 = demographics.get("DX_B", "")
        dx3 = demographics.get("DX_C", "")
        place_value(screen, dx2, 2, 36)
        place_value(screen, dx3, 2, 49)

        n_line = _key_hcfa_service_lines(
            screen, service_lines, n_line, total_lines, grouping, two_lines_only,
            bypass_on=False, use_inel_oi_bundle=False, plain_discount_uses_908=True,
        )

        drafts_created += 1
        send_enter(screen)
        if is_screen(screen, "CPS445.01"):
            send_enter(screen)
            place_value(screen, "x", 29, 76)
            send_enter(screen)

        if not is_screen(screen, "CPS506.01"):
            return _cancel(screen, (screen.GetString(31, 1, 80) or "").strip())

        note = f"{'NEWBORN SPLIT UNDER MOM ' if newborn_type == 'NEW BORN' else 'SPLIT MACRO '}{drafts_created}"
        place_value(screen, RLS_CODE, 3, 13)
        place_value(screen, LST_RLS, 3, 39)
        place_value(screen, PEND_RSN, 3, 53)
        place_value(screen, FLUP_DAYS, 4, 38)
        place_value(screen, PAYEE, 7, 8)
        place_value(screen, note, 4, 50)
        send_enter(screen)
        send_pf(screen, 8)
        place_value(screen, "450", 2, 37)
        send_enter(screen)

    send_pf(screen, 9)
    return {"status": "DONE.", "notes": f"DRAFTS CREATED: {drafts_created}", "drafts_created": drafts_created}


# ---------------------------------------------------------------------------
# Shared internals
# ---------------------------------------------------------------------------

def _cancel(screen, notes: str) -> dict:
    send_pf(screen, 9)
    return {"status": "CANCELLED.", "notes": notes, "drafts_created": 0}


def _split_supplier_name(supplier_name: str) -> tuple[str, str]:
    parts = (supplier_name or "").split()
    if not parts:
        return "", ""
    return parts[0], parts[-1]


def _select_ind_seq_no(screen, claim_row: dict, patient_name: str, patient_dob: str = "") -> bool:
    """
    Mirrors the Screen_220 IndSeqNo-selection block shared by
    hcfa_scratch_split / hcfa_scratch_not_online: by newborn-type
    (IN/SP + sex F), by an explicit NON_NEWBORN_SEQ, or by name(+DOB) match.
    """
    newborn_type = claim_row.get("NEWBORN_TYPE", "")
    for j in range(9, 23, 2):
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
            if len(row_seq) <= 1:
                return False
            first_name_match = (screen.GetString(j, 5, 11) or "").strip() in (patient_name or "")
            dob_match = True
            if patient_dob:
                dob_match = (screen.GetString(j, 37, 6) or "").strip() in (patient_dob or "")
            if first_name_match and dob_match:
                place_value(screen, row_seq, 2, 6)
                return True
    return False


def _match_billing_address(screen, demographics: dict) -> None:
    """Mirrors the MatchBillingAdr loop shared by both Scratch routines."""
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


def _resolve_cond_onset_and_past_term_edits(screen) -> None:
    """
    Mirrors the "PRIOR TO CND ONSET" / "PMNT PAST TERM" edit-retry blocks
    repeated in HCFA_NonScratch_Split — resolved in place, loops until
    neither edit is showing.
    """
    while is_screen(screen, "CPS450.01"):
        edit = (screen.GetString(31, 1, 80) or "").strip()
        if "PRIOR TO CND ONSET" in edit:
            sad = edit[:6]
            row = {"SAD 01": 5, "SAD 02": 7, "SAD 03": 9, "SAD 04": 11}.get(sad)
            if row is None:
                return
            bgn_cnd = (screen.GetString(row, 4, 6) or "").strip()
            place_value(screen, "x", 29, 41)
            send_enter(screen)
            place_value(screen, bgn_cnd, 5, 24)
            send_enter(screen)
            continue
        if "PMNT PAST TERM" in edit:
            sad = edit[:6]
            row = {"SAD 01": (5, 14), "SAD 02": (7, 15), "SAD 03": (9, 16), "SAD 04": (11, 17)}.get(sad)
            if row is None:
                return
            svc_row, inel_row = row
            place_value(screen, (screen.GetString(svc_row, 21, 11) or "").strip(), inel_row, 2)
            place_value(screen, "033", inel_row, 14)
            send_enter(screen)
            continue
        return


def _key_hcfa_service_lines(
    screen, service_lines: list[dict], n_line: int, total_lines: int,
    grouping: str, two_lines_only: bool, *,
    bypass_on: bool, use_inel_oi_bundle: bool, plain_discount_uses_908: bool = False,
) -> int:
    """
    Keys as many consecutive service lines as fit on one CPS450 screen (up
    to 4 lines, or 2 if `two_lines_only`), stopping early at a grouping
    boundary (date-of-service or diagnosis change) or a claim-number change
    — mirrors the shared inner `For i = 5 To 12 Step 2` loop repeated in all
    three split routines. Returns the index of the next unplaced line.

    `use_inel_oi_bundle=True` is the Scratch-mode path: a matched
    INEL_OI_BUNDLE (from get_claim_inel_oi) drives the full inel/OI/BN
    field set, falling back to a bare "001" Inel Code 1 when no bundle
    matched that line. Otherwise (Non-Scratch / Scratch-Not-Online), each
    line's own discount (CPS_DISCOUNT or DISCOUNT_INELIGIBLE) is keyed as a
    plain Inel Amt1/Cd1 pair via `_service_line_charge_for_split`.
    """
    screen_rows = (5, 7, 9, 11)
    line_ctr = 0
    ccn = service_lines[n_line].get("CLAIM_NO") if n_line < total_lines else None
    group_key = (
        service_lines[n_line].get("DOS_FROM") if grouping == "BY DATE OF SERVICE"
        else service_lines[n_line].get("DX_CODE")
    ) if n_line < total_lines else None

    for row in screen_rows:
        if two_lines_only and line_ctr >= 2:
            break
        if n_line >= total_lines:
            break
        svl = service_lines[n_line]

        place_value(screen, svl.get("DOS_FROM", ""), row, 4)
        place_value(screen, svl.get("DOS_TO", ""), row, 11)
        place_value(screen, svl.get("TOS", ""), row, 18)
        place_value(screen, svl.get("CHARGES", ""), row, 21)
        place_value(screen, svl.get("DAYS_UNITS", ""), row, 33)
        place_value(screen, svl.get("CPT_HCPCS", ""), row, 41)
        place_value(screen, svl.get("MOD_A", ""), row, 47)
        place_value(screen, svl.get("MOD_B", ""), row, 51)
        place_value(screen, svl.get("MOD_C", ""), row, 55)
        place_value(screen, svl.get("MOD_D", ""), row, 59)
        place_value(screen, svl.get("DX_CODE", ""), row + 1, 70)

        inel_row = row + 9  # 14/15/16/17 for rows 5/7/9/11
        bundle = svl.get("INEL_OI_BUNDLE", "") if use_inel_oi_bundle else ""
        if use_inel_oi_bundle and bundle:
            _key_inel_oi_bundle(screen, bundle, row, inel_row, bypass_on)
        elif use_inel_oi_bundle:
            place_value(screen, BYPASS_CODE, inel_row, 14)
        else:
            amt, code = _service_line_charge_for_split(svl, {})
            if amt:
                place_value(screen, amt, inel_row, 2)
                place_value(screen, code or (INEL_CODE if plain_discount_uses_908 else BYPASS_CODE), inel_row, 14)
                place_value(screen, BYPASS_CODE, inel_row, 30)
            else:
                place_value(screen, BYPASS_CODE, inel_row, 14)

        n_line += 1
        line_ctr += 1
        if n_line >= total_lines:
            break
        next_svl = service_lines[n_line]
        if next_svl.get("CLAIM_NO") != ccn:
            break
        next_key = next_svl.get("DOS_FROM") if grouping == "BY DATE OF SERVICE" else next_svl.get("DX_CODE")
        if next_key != group_key:
            break

    return n_line


def _key_inel_oi_bundle(screen, bundle: str, row: int, inel_row: int, bypass_on: bool) -> None:
    """Places a Scratch-mode INEL_OI_BUNDLE string (see get_claim_inel_oi) onto the current draft's line."""
    try:
        inel1, inel2, oi = bundle.split("|")
        amt1, cd1 = inel1.split("-")
        amt2, cd2 = inel2.split("-")
        oi_elig, oi_paid, oi_type, bn, bn_amt, sp, ndc = oi.split("-")
    except ValueError:
        place_value(screen, BYPASS_CODE, inel_row, 14)
        return

    place_value(screen, amt1, inel_row, 2)
    place_value(screen, cd1, inel_row, 14)
    place_value(screen, amt2, inel_row, 18)
    place_value(screen, cd2, inel_row, 30)
    oi_row = inel_row + 6
    place_value(screen, oi_elig, oi_row, 4)
    place_value(screen, oi_paid, oi_row, 16)
    place_value(screen, oi_type, oi_row, 28)
    place_value(screen, bn, oi_row, 31)
    place_value(screen, bn_amt, oi_row, 36)
    place_value(screen, sp, oi_row, 48)
    place_value(screen, ndc, oi_row, 56)
    if bypass_on:
        place_value(screen, BYPASS_CODE, inel_row, 30)
