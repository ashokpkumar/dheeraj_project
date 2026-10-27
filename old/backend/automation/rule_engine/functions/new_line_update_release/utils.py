"""
NEW.LINE.UPDATE.RELEASE macro — screen data-entry helpers.

Ports Line_Update_Release / ClaimDraft_SVCLn_Update / No_SVCLn_Update /
Place_EOB_Notes / IS_IT_MATCHING / RTN_PND_CODE / OOP_Claim / SetInelCdList /
MED_CALC_SETTINGS / MRU_CALC_SETTINGS from Macro/oWauben.txt (VBA).

The mainframe screen primitives (PF-keys, MoveTo/EraseEOF/PutString, the
CPS520.01 claim-entry loop) are identical to release_pend_macro's — both
macros drive the same CPS claim screens — so they're imported from there
instead of being duplicated.

IBM PCOMM was not ported: none of the other macros in this codebase
(release_pend_macro, same_day_reversal, OI_YES_NO) implement the PCOMM
branch either, only REFLECTION/EXTRA.
"""

import pandas as pd

from rule_engine.functions.release_pend_macro.utils import (  # noqa: F401
    get_screen_id,
    pf9_to_cps520,
    place_value,
    remove_value,
    send_enter,
    send_pf,
    wait_ready,
)


# ---------------------------------------------------------------------------
# IS_IT_MATCHING VBA port
# ---------------------------------------------------------------------------
def is_it_matching(value1: str, value2: str) -> bool:
    """A blank `value1` is treated as "don't care" and always matches."""
    value1 = (value1 or "").strip()
    if not value1:
        return True
    return value1 == (value2 or "").strip()


# ---------------------------------------------------------------------------
# Place_EOB_Notes VBA port
# ---------------------------------------------------------------------------
def place_eob_notes(screen, note: str, start_row: int = 16, col: int = 36):
    """Word-wraps note text (max 43 chars/line) across the CPS506 note lines."""
    note = (note or "").strip()
    if not note:
        return
    words = note.split()
    row = start_row
    line = ""
    for word in words:
        candidate = (line + " " + word).strip()
        if len(candidate) > 43:
            place_value(screen, line, row, col)
            line = word
            row += 1
        else:
            line = candidate
    if line:
        place_value(screen, line, row, col)


# ---------------------------------------------------------------------------
# RTN_PND_CODE VBA port
# ---------------------------------------------------------------------------
def rtn_pnd_code(screen, ln_no: str) -> str:
    """Reads the pend code next to a given draft line number (e.g. '01')."""
    for i in range(6, 19, 2):
        if (screen.GetString(i, 2, 2) or "").strip() == ln_no:
            return (screen.GetString(i, 6, 2) or "").strip()
    return ""


# ---------------------------------------------------------------------------
# No_SVCLn_Update VBA port
# ---------------------------------------------------------------------------
def no_svcln_update(screen, inel_code: str, claim_type: str) -> bool:
    """
    True when EVERY populated service line on the current draft already
    carries `inel_code` as its ineligibility code — i.e. there's nothing to
    update and the draft can be released as-is.
    """
    matched_all = True
    read_count = 0
    if claim_type == "UB":
        for i in range(6, 10):
            if not (screen.GetString(i, 3, 4) or "").strip():
                break
            if (screen.GetString(i + 6, 14, 4) or "").strip() != inel_code:
                matched_all = False
            read_count += 1
    elif claim_type == "HCFA":
        L = 9
        for i in range(5, 12, 2):
            if not (screen.GetString(i, 4, 6) or "").strip():
                break
            if (screen.GetString(i + L, 14, 4) or "").strip() != inel_code:
                matched_all = False
            read_count += 1
    return matched_all and read_count > 0


# ---------------------------------------------------------------------------
# OOP_Claim VBA port
# ---------------------------------------------------------------------------
def oop_claim(lines: list) -> bool:
    """
    Flags a claim as a possible out-of-network claim when any of its
    service lines carry a negative NEW_INEL1_AMOUNT.

    NOTE: the original VBA (`OOP_Claim`) filters a hardcoded column index
    (Field:=14) that predates the 2026.03.10 insertion of the MOD 03 column
    (colMod3) — after that insert, Field:=14 lines up with MOD 03, not with
    NEW INEL1 AMOUNT (colNwAmt) as the function name/intent implies. This
    port uses NEW_INEL1_AMOUNT (the semantically-correct field) rather than
    reproducing what looks like a stale off-by-one in the original macro.
    """
    for ln in lines:
        try:
            if float(str(ln.get("NEW_INEL1_AMOUNT", "") or 0).strip() or 0) < 0:
                return True
        except (ValueError, TypeError):
            continue
    return False


# ---------------------------------------------------------------------------
# CPS506 release/pend entry — mirrors the CPS506 block in Line_Update_Release
# (kept separate from release_pend_macro's data_entry_in_cps506: this macro
# also enters DCI at 5,39 and doesn't use release_pend's payee-2/3 sub-fields)
# ---------------------------------------------------------------------------
def data_entry_cps506_line_update(screen, row: dict, settings: dict):
    place_value(screen, settings.get("rls_code", ""), 3, 13)
    place_value(screen, settings.get("lst_rls", ""), 3, 39)
    place_value(screen, settings.get("pnd_rsn", ""), 3, 53)
    place_value(screen, settings.get("pnd_op_id", ""), 4, 13)
    # ROUTE TO CFR/OPID (claim-level, from DB/file) overrides the rule default
    if str(row.get("ROUTE_TO_OPID", "") or "").strip():
        place_value(screen, row.get("ROUTE_TO_OPID", ""), 4, 13)
    place_value(screen, settings.get("flw_up_days", ""), 4, 38)
    place_value(screen, settings.get("note", ""), 4, 50)
    place_value(screen, settings.get("eob", ""), 5, 24)
    place_value(screen, settings.get("ck", ""), 5, 31)
    place_value(screen, settings.get("dci", ""), 5, 39)
    place_value(screen, str(settings.get("payee", "0")), 7, 8)
    place_eob_notes(screen, settings.get("eob_note", ""))


# ---------------------------------------------------------------------------
# ClaimDraft_SVCLn_Update VBA port — HCFA branch
# ---------------------------------------------------------------------------
def update_hcfa_service_lines(screen, lines: list, settings: dict, hcfa_inelcd: set, exception_codes: set) -> tuple:
    """
    Mirrors the "Case HCFA" branch of ClaimDraft_SVCLn_Update.
    `lines` are the unmatched (no '_STATUS') service-line dict rows for this
    claim. Mutates matched rows in place (_STATUS='DONE').
    Returns (matched: bool, message: str).
    """
    new_pos = str(settings.get("new_pos", "") or "").strip()
    if new_pos:
        place_value(screen, new_pos, 2, 6)

    inel_cd_fld = settings.get("inel_cd_fld", "1")
    inel_code_val = settings.get("inel_code_val", "")
    inel2_option = settings.get("inel2_option", "")
    apply_oi_amt = settings.get("apply_oi_amt", "N") == "Y"
    oi_calc_type = settings.get("oi_calc_type", "")

    L, p = 9, 15
    matched_any = False

    for i in range(5, 12, 2):
        if not (screen.GetString(i, 4, 6) or "").strip():
            L -= 1
            p -= 1
            continue

        for ln in lines:
            if ln.get("_STATUS"):
                continue

            if settings.get("apply_inel_cd_exceptions", "N") == "Y":
                if (screen.GetString(i + L, 14, 4) or "").strip() in exception_codes:
                    matched_any = True
                    break  # this screen slot is exempt; move to next slot

            screen_inel = (screen.GetString(i + L, 14, 4) or "").strip()
            if screen_inel not in hcfa_inelcd:
                return False, "CCN REJECTED:INELCODE NOT MATCHED"

            bg_dt = str(ln.get("BGN_SV_DT", "") or "").strip()
            cpt = str(ln.get("CPT", "") or "").strip()
            units = str(ln.get("UNITS", "") or "").strip()
            chrg_amt = str(ln.get("LINE_CHG_AMT", "") or "").strip()
            mod01 = str(ln.get("MOD01", "") or "").strip()
            mod02 = str(ln.get("MOD02", "") or "").strip()
            mod03 = str(ln.get("MOD03", "") or "").strip()

            if not bg_dt or not chrg_amt:
                continue
            if not is_it_matching(bg_dt, screen.GetString(i, 4, 6)):
                continue
            if not is_it_matching(cpt, screen.GetString(i, 41, 5)):
                continue
            if units and not is_it_matching(units, screen.GetString(i, 33, 5)):
                continue
            if not is_it_matching(chrg_amt, screen.GetString(i, 21, 11)):
                continue
            if mod01 and not is_it_matching(mod01, screen.GetString(i, 47, 3)):
                continue
            if mod02 and not is_it_matching(mod02, screen.GetString(i, 51, 3)):
                continue
            if mod03 and not is_it_matching(mod03, screen.GetString(i, 55, 3)):
                continue

            # -- match found: apply the new values --
            place_value(screen, ln.get("NEW_CHRG_AMT", ""), i, 21)
            place_value(screen, ln.get("AP", ""), i + p, 68)
            place_value(screen, ln.get("NEW_MOD01", ""), i, 47)
            place_value(screen, ln.get("NEW_MOD02", ""), i, 51)
            place_value(screen, ln.get("NEW_MOD03", ""), i, 55)

            if inel_cd_fld in ("1", ""):
                place_value(screen, ln.get("NEW_INEL1_AMOUNT", ""), i + L, 2)
                place_value(screen, ln.get("NEW_INEL1_CD", "") or inel_code_val, i + L, 14)
            elif inel_cd_fld == "2":
                place_value(screen, ln.get("NEW_INEL1_AMOUNT", ""), i + L, 18)
                place_value(screen, ln.get("NEW_INEL1_CD", "") or inel_code_val, i + L, 30)
            elif inel_cd_fld == "BOTH":
                place_value(screen, ln.get("NEW_INEL1_AMOUNT", ""), i + L, 2)
                place_value(screen, ln.get("NEW_INEL1_CD", ""), i + L, 14)
                place_value(screen, ln.get("NEW_INEL2_AMOUNT", ""), i + L, 18)
                place_value(screen, ln.get("NEW_INEL2_CD", ""), i + L, 30)

            if inel2_option == "APPLY 001 INELCD2":
                place_value(screen, "001", i + L, 30)

            place_value(screen, ln.get("PROV_RATE", ""), i + L, 50)
            place_value(screen, ln.get("SMB_ADJ_AMT", ""), i + L, 62)
            place_value(screen, ln.get("SMB_ADJ_REASON", ""), i + L, 74)

            if apply_oi_amt:
                place_value(screen, ln.get("OI_ELIG_AMT", ""), i + L + 6, 5)
                place_value(screen, ln.get("OI_PAID_AMT", ""), i + L + 6, 16)
                if oi_calc_type == "TYPE B":
                    place_value(screen, "B", i + L + 6, 26)

            if str(ln.get("OI_TYPE", "") or "").strip():
                place_value(screen, ln.get("OI_TYPE", ""), i + L + 6, 26)
            if str(ln.get("BU", "") or "").strip():
                place_value(screen, ln.get("BU", ""), i, 32)
            if str(ln.get("IU", "") or "").strip():
                place_value(screen, ln.get("IU", ""), i, 36)
            if str(ln.get("NEW_TOS", "") or "").strip():
                place_value(screen, ln.get("NEW_TOS", ""), i, 14)

            ln["_STATUS"] = "DONE"
            matched_any = True
            break

        L -= 1
        p -= 1

    if not matched_any:
        return False, "FAILED:NO SERVICE LINE LISTED" if not lines else "CCN REJECTED:INELCODE NOT MATCHED"
    return True, ""


# ---------------------------------------------------------------------------
# ClaimDraft_SVCLn_Update VBA port — UB branch
# ---------------------------------------------------------------------------
def update_ub_service_lines(screen, lines: list, settings: dict, ub_inelcd: set, exception_codes: set) -> tuple:
    """Mirrors the "Case UB" branch of ClaimDraft_SVCLn_Update."""
    if settings.get("apply_rp_bypass_precert", "N") == "Y":
        place_value(screen, "RP", 2, 5)

    if settings.get("change_from_to_dates", "N") == "Y":
        from_date = (screen.GetString(2, 63, 6) or "").strip()
        thru_date = (screen.GetString(2, 75, 6) or "").strip()
        serv_date = (screen.GetString(6, 17, 6) or "").strip()
        if from_date != serv_date:
            place_value(screen, serv_date, 2, 63)
        if thru_date != serv_date:
            place_value(screen, serv_date, 2, 75)

    inel_cd_fld = settings.get("inel_cd_fld", "1")
    inel_code_val = settings.get("inel_code_val", "")
    inel2_option = settings.get("inel2_option", "")
    apply_oi_amt = settings.get("apply_oi_amt", "N") == "Y"
    oi_calc_type = settings.get("oi_calc_type", "")

    a = 0
    matched_any = False

    for i in range(6, 10):
        if not (screen.GetString(i, 3, 4) or "").strip():
            break

        for ln in lines:
            if ln.get("_STATUS"):
                continue

            if settings.get("apply_inel_cd_exceptions", "N") == "Y":
                if (screen.GetString(i + 6, 14, 4) or "").strip() in exception_codes:
                    matched_any = True
                    break

            screen_inel = (screen.GetString(i + 6, 14, 4) or "").strip()
            if screen_inel not in ub_inelcd:
                return False, "CCN REJECTED:INELCODE NOT MATCHED"

            bg_dt = str(ln.get("BGN_SV_DT", "") or "").strip()
            cpt = str(ln.get("CPT", "") or "").strip()
            units = str(ln.get("UNITS", "") or "").strip()
            chrg_amt = str(ln.get("LINE_CHG_AMT", "") or "").strip()
            mod01 = str(ln.get("MOD01", "") or "").strip()
            mod02 = str(ln.get("MOD02", "") or "").strip()
            mod03 = str(ln.get("MOD03", "") or "").strip()

            if not bg_dt or not chrg_amt:
                continue
            if not is_it_matching(bg_dt, screen.GetString(i, 17, 6)):
                continue
            if cpt and not is_it_matching(cpt, screen.GetString(i, 8, 5)):
                continue
            if units and not is_it_matching(units, screen.GetString(i, 32, 3)):
                continue
            if not is_it_matching(chrg_amt, screen.GetString(i, 40, 11)):
                continue
            if mod01 and not is_it_matching(mod01, screen.GetString(i, 52, 3)):
                continue
            if mod02 and not is_it_matching(mod02, screen.GetString(i, 56, 3)):
                continue
            if mod03 and not is_it_matching(mod03, screen.GetString(i, 60, 3)):
                continue

            # -- match found: apply the new values --
            place_value(screen, ln.get("NEW_CHRG_AMT", ""), i, 40)
            place_value(screen, ln.get("AP", ""), 10, 54 + a)
            place_value(screen, ln.get("NEW_MOD01", ""), i, 52)
            place_value(screen, ln.get("NEW_MOD02", ""), i, 56)
            place_value(screen, ln.get("NEW_MOD03", ""), i, 60)

            if inel_cd_fld in ("1", ""):
                place_value(screen, ln.get("NEW_INEL1_AMOUNT", ""), i + 6, 2)
                place_value(screen, ln.get("NEW_INEL1_CD", "") or inel_code_val, i + 6, 14)
            elif inel_cd_fld == "2":
                place_value(screen, ln.get("NEW_INEL1_AMOUNT", ""), i + 6, 18)
                place_value(screen, ln.get("NEW_INEL1_CD", "") or inel_code_val, i + 6, 30)
            elif inel_cd_fld == "BOTH":
                place_value(screen, ln.get("NEW_INEL1_AMOUNT", ""), i + 6, 2)
                place_value(screen, ln.get("NEW_INEL1_CD", ""), i + 6, 14)
                place_value(screen, ln.get("NEW_INEL2_AMOUNT", ""), i + 6, 18)
                place_value(screen, ln.get("NEW_INEL2_CD", ""), i + 6, 30)

            if inel2_option == "APPLY 001 INELCD2":
                place_value(screen, "001", i + 6, 30)

            place_value(screen, ln.get("PROV_RATE", ""), i + 6, 50)
            place_value(screen, ln.get("SMB_ADJ_AMT", ""), i + 6, 62)
            place_value(screen, ln.get("SMB_ADJ_REASON", ""), i + 6, 74)

            if apply_oi_amt:
                place_value(screen, ln.get("OI_ELIG_AMT", ""), i + 12, 2)
                place_value(screen, ln.get("OI_PAID_AMT", ""), i + 12, 14)
                if oi_calc_type == "TYPE B":
                    place_value(screen, "B", i + 12, 26)

            if str(ln.get("OI_TYPE", "") or "").strip():
                place_value(screen, ln.get("OI_TYPE", ""), i + 12, 26)
            if str(ln.get("BU", "") or "").strip():
                place_value(screen, ln.get("BU", ""), i, 32)
            if str(ln.get("IU", "") or "").strip():
                place_value(screen, ln.get("IU", ""), i, 36)
            if str(ln.get("NEW_TOS", "") or "").strip():
                place_value(screen, ln.get("NEW_TOS", ""), i, 14)

            ln["_STATUS"] = "DONE"
            matched_any = True
            break

        a += 3

    if not matched_any:
        return False, "FAILED:NO SERVICE LINE LISTED" if not lines else "CCN REJECTED:INELCODE NOT MATCHED"
    return True, ""


# ---------------------------------------------------------------------------
# SetInelCdList / MED_CALC_SETTINGS / MRU_CALC_SETTINGS VBA port
# Reads the REFERENCE-sheet equivalent (positional columns, mirrors
# Macro/Reference layout: A/B ineligibility code lists, D-G med-calc table,
# J-M mru-calc table, N in-network POS list, P exception inel codes).
# ---------------------------------------------------------------------------
def _pct_to_float(val) -> float:
    val = str(val or "").strip().replace("%", "")
    if not val:
        return 0.0
    try:
        num = float(val)
    except ValueError:
        return 0.0
    # Values authored as "43.76" (i.e. already meant as 43.76%) get divided
    # down to a fraction; values already authored as a fraction (0.4376)
    # are left as-is.
    return num / 100 if num > 1 else num


def load_line_update_reference(path: str) -> dict:
    """
    Returns a dict with:
      hcfa_inelcd, ub_inelcd, exception_inel_codes : set[str]
      mru_innetwork_pos                            : set[str]
      med_calc   : {claim_no: (ded_coin_eob, neg_contractual, noncov)}
      mru_calc   : {year+state: (ip_pct, out_pct)}
    "BLANK" literal entries (as in the VBA HCFA/UB code lists) map to "".
    """
    if str(path).lower().endswith(".csv"):
        df = pd.read_csv(path, dtype=str)
    else:
        df = pd.read_excel(path, dtype=str)
    df.columns = [str(c).strip().upper() for c in df.columns]

    def col(name):
        if name not in df.columns:
            return pd.Series(dtype=str)
        return df[name]

    def code_set(name):
        result = set()
        for v in col(name).dropna():
            v = str(v).strip()
            if not v:
                continue
            result.add("" if v.upper() == "BLANK" else v)
        return result

    med_calc = {}
    if "MED_CALC_CLAIM_NO" in df.columns:
        for _, row in df.iterrows():
            claim_no = str(row.get("MED_CALC_CLAIM_NO", "") or "").strip()
            if not claim_no or claim_no.lower() == "nan":
                continue
            if claim_no not in med_calc:
                med_calc[claim_no] = (
                    str(row.get("MED_CALC_DED_COIN_EOB", "") or "0").strip(),
                    str(row.get("MED_CALC_NEG_CONTRACTUAL", "") or "0").strip(),
                    str(row.get("MED_CALC_NONCOV", "") or "0").strip(),
                )

    mru_calc = {}
    if "MRU_YEAR" in df.columns:
        for _, row in df.iterrows():
            year = str(row.get("MRU_YEAR", "") or "").strip()
            state = str(row.get("MRU_STATE", "") or "").strip()
            if not year or year.lower() == "nan":
                continue
            key = f"{year}{state}"
            if key not in mru_calc:
                mru_calc[key] = (
                    _pct_to_float(row.get("MRU_IP_PCT", "")),
                    _pct_to_float(row.get("MRU_OUT_PCT", "")),
                )

    return {
        "hcfa_inelcd": code_set("HCFA_INELCD"),
        "ub_inelcd": code_set("UB_INELCD"),
        "exception_inel_codes": code_set("EXCEPTION_INEL_CODES"),
        "mru_innetwork_pos": {v.zfill(2) for v in code_set("MRU_INNETWORK_POS")},
        "med_calc": med_calc,
        "mru_calc": mru_calc,
    }
