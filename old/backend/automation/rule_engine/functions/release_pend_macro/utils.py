import pandas as pd


# ---------------------------------------------------------------------------
# Screen primitives (mirror VBA helpers in Modules_oShared.txt)
# ---------------------------------------------------------------------------

def wait_ready(screen):
    while screen.OIA.XStatus != 0:
        pass


def get_screen_id(screen) -> str:
    return (screen.GetString(1, 2, 11) or "").strip()


def place_value(screen, val, r: int, c: int):
    val = ("" if val is None else str(val)).strip()
    if not val:
        return
    wait_ready(screen)
    screen.MoveTo(r, c)
    wait_ready(screen)
    screen.SendKeys("<EraseEOF>")
    wait_ready(screen)
    screen.PutString(val, r, c)
    wait_ready(screen)


def remove_value(screen, r: int, c: int):
    wait_ready(screen)
    screen.MoveTo(r, c)
    wait_ready(screen)
    screen.SendKeys("<EraseEOF>")
    wait_ready(screen)


def send_enter(screen):
    screen.SendKeys("<Enter>")
    wait_ready(screen)


def send_pf(screen, n: int):
    screen.SendKeys(f"<PF{n}>")
    wait_ready(screen)


def pf9_to_cps520(screen, max_tries: int = 15) -> bool:
    for _ in range(max_tries):
        if get_screen_id(screen) == "CPS520.01":
            return True
        send_pf(screen, 9)
    return get_screen_id(screen) == "CPS520.01"


# ---------------------------------------------------------------------------
# Code reference loader — reads dx_code_ref_excel.xlsx
# Column mapping mirrors VBA DxCodesRef sheet
# ---------------------------------------------------------------------------

def load_code_refs(xlsx_path: str) -> dict:
    df = pd.read_excel(xlsx_path, header=0)

    def col_set(col_idx: int) -> set:
        """Return non-empty stripped strings from zero-based column index."""
        if col_idx >= len(df.columns):
            return set()
        return {str(v).strip() for v in df.iloc[:, col_idx].dropna() if str(v).strip()}

    def col_dict(col_idx: int) -> dict:
        s = col_set(col_idx)
        return {v: v for v in s}

    def price_dict(code_col: int, price_col: int) -> dict:
        """Build {cpt_code: price} for grid price validation."""
        result = {}
        if code_col >= len(df.columns) or price_col >= len(df.columns):
            return result
        for _, row in df.iterrows():
            code = str(row.iloc[code_col]).strip() if pd.notna(row.iloc[code_col]) else ""
            price = row.iloc[price_col] if pd.notna(row.iloc[price_col]) else None
            if code and price is not None:
                result[code] = float(price)
        return result

    return {
        "dx_codes":           col_dict(0),   # col A – ICD10-CM DX CODES
        "lab_codes":          col_dict(1),   # col B – LAB CPT CODES
        "ub_rev_codes":       col_dict(2),   # col C – UB REV CODES
        "grid_price":         price_dict(4, 5),  # col E/F – CPT / GRID PRICE
        "rejected_inel":      col_dict(7),   # col H – rejected inel codes
        "mod_codes":          col_dict(9),   # col J – modifier codes
        "dny_by_cpt":         col_dict(10),  # col K – CPT denial codes
        "dnl_inel_exceptions":col_dict(13),  # col N – denial inel exceptions
        "ck_inel":            col_dict(15),  # col P – check inel dict
        "apply_disc_after_dnl":col_dict(17), # col R – apply disc after denial codes
        "rem_disc_amt":       col_dict(19),  # col T – remove discount amt inel codes
        "possible_hcr":       col_dict(21),  # col V – possible HCR CPT codes
        "cpt_codes_full_pd":  col_dict(23),  # col X – CPT codes for full-paid validation
        "lab_cpt_codes_by_rule": _load_lab_cpt_codes_by_rule(xlsx_path),
    }


def _load_lab_cpt_codes_by_rule(xlsx_path: str) -> dict:
    """
    Reads the 'lab_cpt_codes' sheet ('rule', 'codes' columns) and returns
    {RULE_UPPER: {code: code, ...}}. The 'codes' cell holds one CPT code per
    line.
    """
    try:
        lab_df = pd.read_excel(xlsx_path, sheet_name="lab_cpt_codes", header=0)
    except (FileNotFoundError, ValueError):
        return {}

    result = {}
    for _, row in lab_df.iterrows():
        rule = str(row.get("rule", "")).strip().upper()
        if not rule or rule == "NAN":
            continue
        codes_cell = row.get("codes", "")
        codes_str = "" if pd.isna(codes_cell) else str(codes_cell)
        code_set = {c.strip() for c in codes_str.splitlines() if c.strip()}
        result[rule] = {c: c for c in code_set}

    return result


# ---------------------------------------------------------------------------
# CPS506 release screen data entry (mirrors Data_Entry_In_Cps506 VBA)
# ---------------------------------------------------------------------------

def data_entry_in_cps506(screen, row: dict, settings: dict):
    place_value(screen, settings.get("rls_code", ""), 3, 13)
    place_value(screen, settings.get("lst_rls", ""), 3, 39)
    place_value(screen, settings.get("pnd_rsn", ""), 3, 53)
    place_value(screen, settings.get("pnd_opid", ""), 4, 13)
    place_value(screen, settings.get("flwup_days", ""), 4, 38)
    place_value(screen, settings.get("note", ""), 4, 50)
    place_value(screen, settings.get("disti_unit", ""), 5, 13)
    place_value(screen, settings.get("eob", ""), 5, 24)
    place_value(screen, settings.get("ck", ""), 5, 31)

    # EOB notes – per-claim overrides global
    eob_note_src = row.get("EOB_PER_CLM", "") or settings.get("eob_note", "")
    if eob_note_src:
        _place_eob_notes(screen, str(eob_note_src))

    place_value(screen, str(settings.get("payee", "0")), 7, 8)

    payee = str(settings.get("payee", "0"))
    if payee == "2":
        place_value(screen, str(row.get("PROV_NAME", ""))[:28], 10, 18)
        addr = str(row.get("PROV_ADD", ""))
        place_value(screen, addr[:38], 11, 18)
        if len(addr) > 38:
            place_value(screen, addr[38:76], 12, 18)
        place_value(screen, str(row.get("CITY", ""))[:20], 13, 18)
        place_value(screen, str(row.get("STATE", ""))[:2], 13, 43)
        place_value(screen, str(row.get("ZIP2", ""))[:6], 13, 52)
    elif payee == "3":
        place_value(screen, f"{float(row.get('SPLIT_EE', 0)):.2f}", 9, 22)
        place_value(screen, f"{float(row.get('SPLIT_PR', 0)):.2f}", 9, 41)


def _place_eob_notes(screen, notes: str):
    words = notes.split()
    row_entry = 16
    line = ""
    for word in words:
        candidate = (line + " " + word).strip()
        if len(candidate) > 44:
            place_value(screen, line, row_entry, 36)
            line = word
            row_entry += 1
        else:
            line = candidate
    if line.strip():
        place_value(screen, line, row_entry, 36)


# ---------------------------------------------------------------------------
# Ineligibility code helper — mirrors IneligiblityCodes VBA
# ---------------------------------------------------------------------------

def apply_ineligibility_codes(screen, claim_type: str, row: dict, settings: dict, dny_by_cpt: dict):
    inel_code = settings.get("inel_code", "")
    if not inel_code:
        return
    if not dny_by_cpt:
        return

    if claim_type == "HCFA":
        lp = 9
        changed = False
        for ln in range(5, 12, 2):
            inel = (screen.GetString(ln, 21, 11) or "").strip()
            cpt = (screen.GetString(ln, 41, 5) or "").strip()
            if cpt in dny_by_cpt:
                if settings.get("dis_aft_dnl", "N") != "Y":
                    place_value(screen, inel, ln + lp, 2)
                    place_value(screen, inel_code, ln + lp, 14)
                    changed = True
            lp -= 1
        if changed:
            send_enter(screen)
            send_pf(screen, 8)
            place_value(screen, "450", 2, 37)
            send_enter(screen)

    elif claim_type == "UB":
        lp = 6
        changed = False
        for ln in range(6, 10):
            inel = (screen.GetString(ln, 40, 11) or "").strip()
            cpt = (screen.GetString(ln, 8, 5) or "").strip()
            if cpt in dny_by_cpt:
                if settings.get("dis_aft_dnl", "N") != "Y":
                    place_value(screen, inel, ln + lp, 2)
                    place_value(screen, inel_code, ln + lp, 14)
                    changed = True
        if changed:
            send_enter(screen)
            send_pf(screen, 8)
            place_value(screen, "460", 2, 37)
            send_enter(screen)


# ---------------------------------------------------------------------------
# apply_631_inel helper — mirrors Apply631Inel VBA
# ---------------------------------------------------------------------------

def apply_631_inel(screen, claim_type: str, code: str):
    if claim_type == "UB":
        for i in range(12, 16):
            for j in (14, 30):
                if (screen.GetString(i, j, 3) or "").strip():
                    place_value(screen, code, i, j)
    elif claim_type == "HCFA":
        for i in range(14, 18):
            for j in (14, 30):
                if (screen.GetString(i, j, 3) or "").strip():
                    place_value(screen, code, i, j)


# ---------------------------------------------------------------------------
# CHECK_INEL_CODE — mirrors CHECK_INEL_CODE VBA
# ---------------------------------------------------------------------------

def check_inel_code(screen, ck_inel: dict) -> tuple:
    """Returns (found: bool, found_codes: str)."""
    found = False
    i_exists = ""
    send_pf(screen, 8)
    place_value(screen, "408", 2, 37)
    send_enter(screen)
    while True:
        for i in range(3, 18, 14):
            if (screen.GetString(31, 2, 70) or "").strip() == "YOU MAY NOT PAGE FORWARD AT THIS TIME":
                goto_506(screen)
                return found, i_exists
            if not (screen.GetString(i, 3, 11) or "").strip():
                break
            for j in range(8, 57, 12):
                inel_code = (screen.GetString(i + 3, j, 5) or "").strip()
                if inel_code in ck_inel:
                    i_exists += inel_code + "|"
                    found = True
                if not inel_code:
                    break
        send_pf(screen, 11)
        if "YOU MAY NOT PAGE FORWARD" in (screen.GetString(31, 2, 60) or "").upper():
            break
    goto_506(screen)
    return found, i_exists


def goto_506(screen):
    send_pf(screen, 8)
    place_value(screen, "506", 2, 37)
    send_enter(screen)


# ---------------------------------------------------------------------------
# Plan ID update — mirrors Plan_ID_UpdateByClaimNo VBA
# ---------------------------------------------------------------------------

def plan_id_update(screen, row: dict) -> str:
    seq_no = str(row.get("SEQ_NO", "") or "").strip()
    new_plan_id = str(row.get("NEW_PLAN_ID", "") or "").strip()
    updt = __import__("datetime").date.today().strftime("%m%d%y")
    tp = "MP"
    family = "YES"

    send_pf(screen, 8)
    screen.PutString("850", 2, 37)
    wait_ready(screen)
    send_enter(screen)
    place_value(screen, "x", 29, 48)
    send_enter(screen)
    place_value(screen, "x", 29, 17)
    wait_ready(screen)
    send_enter(screen)

    for x in range(4, 25, 5):
        mbr = (screen.GetString(x, 2, 2) or "").strip()
        if not mbr:
            break
        if mbr == f"{int(seq_no):02d}":
            place_value(screen, family, 2, 18)
            place_value(screen, updt, 2, 29)
            place_value(screen, updt, x, 30)
            place_value(screen, tp, x, 37)
            place_value(screen, new_plan_id, x, 54)
            send_enter(screen)
            msg = (screen.GetString(30, 2, 79) or screen.GetString(31, 2, 79) or "").strip()
            return msg or "PLAN ID FIELD UPDATED."

    return "NO MATCHING SEQ NO."


# ---------------------------------------------------------------------------
# Is_It_Fully_Paid — mirrors Is_It_Fully_Paid VBA
# ---------------------------------------------------------------------------

def is_fully_paid(screen, by_what: str, rejected_inel: dict, cpt_codes_full_pd: dict) -> tuple:
    """Returns (is_paid: bool, msg: str)"""
    send_pf(screen, 8)
    place_value(screen, "408", 2, 37)
    send_enter(screen)

    while True:
        for ln in (5, 19):
            chg_str = (screen.GetString(ln, 26, 9) or "").strip()
            if not chg_str:
                break
            try:
                t_charge = float(chg_str)
                t_paid = float((screen.GetString(ln + 5, 72, 9) or "0").strip())
            except ValueError:
                continue

            if by_what == "InelCodes":
                cd1 = (screen.GetString(ln + 1, 10, 3) or "").strip()
                cd2 = (screen.GetString(ln + 1, 22, 3) or "").strip()
                cd3 = (screen.GetString(ln + 1, 34, 3) or "").strip()
                if cd1 in rejected_inel or cd2 in rejected_inel or cd3 in rejected_inel:
                    _back_to_506(screen)
                    return False, f"REJECTED INELCODES ON 100% PD:{cd1}|{cd2}|{cd3}"
                non_zero = [c for c in (cd1, cd2, cd3) if c and c != "000"]
                if len(non_zero) > 1:
                    _back_to_506(screen)
                    return False, "MORE THAN 1 INEL CODES"
                t_discount = 0.0
                if cd1 != "000":
                    t_discount = float((screen.GetString(ln + 2, 4, 9) or "0").strip())
                elif cd2 != "000":
                    t_discount = float((screen.GetString(ln + 2, 16, 9) or "0").strip())
                elif cd3 != "000":
                    t_discount = float((screen.GetString(ln + 2, 28, 9) or "0").strip())
                if "311" in (cd1, cd2, cd3):
                    t_oi_el = float((screen.GetString(ln + 8, 3, 10) or "0").strip())
                    t_oi_pd = float((screen.GetString(ln + 8, 15, 10) or "0").strip())
                    if round(t_paid, 2) != round(t_oi_el - t_oi_pd, 2):
                        _back_to_506(screen)
                        return False, ""
                else:
                    if round(t_charge, 2) != round(t_discount + t_paid, 2):
                        _back_to_506(screen)
                        return False, ""

            elif by_what == "CPTCodes":
                cpt = (screen.GetString(ln, 42, 5) or "").strip()
                if cpt in cpt_codes_full_pd:
                    cd1 = (screen.GetString(ln + 1, 10, 3) or "").strip()
                    cd2 = (screen.GetString(ln + 1, 22, 3) or "").strip()
                    cd3 = (screen.GetString(ln + 1, 34, 3) or "").strip()
                    t_discount = 0.0
                    if cd1 != "000":
                        t_discount = float((screen.GetString(ln + 2, 4, 9) or "0").strip())
                    elif cd2 != "000":
                        t_discount = float((screen.GetString(ln + 2, 16, 9) or "0").strip())
                    elif cd3 != "000":
                        t_discount = float((screen.GetString(ln + 2, 28, 9) or "0").strip())
                    if round(t_charge, 2) != round(t_discount + t_paid, 2):
                        _back_to_506(screen)
                        return False, ""

        if "F11" in (screen.GetString(29, 69, 11) or ""):
            send_pf(screen, 11)
            if "YOU MAY NOT PAGE FORWARD AT THIS TIME" in (screen.GetString(31, 2, 60) or "").upper():
                break
        else:
            break

    _back_to_506(screen)
    return True, ""


def _back_to_506(screen):
    send_pf(screen, 8)
    place_value(screen, "506", 2, 37)
    send_enter(screen)


# ---------------------------------------------------------------------------
# Total_Amt_858 — mirrors Total_Amt_858 VBA
# ---------------------------------------------------------------------------

def total_amt_858(screen) -> str:
    amt = 0.0
    inel_to_read = {"858", "700"}
    send_pf(screen, 8)
    place_value(screen, "408", 2, 37)
    send_enter(screen)
    while True:
        for ln in (5, 19):
            if not (screen.GetString(ln, 26, 9) or "").strip():
                break
            for j, pos in ((10, 3), (22, 15), (34, 27)):
                if (screen.GetString(ln + 1, j, 3) or "").strip() in inel_to_read:
                    try:
                        amt += float((screen.GetString(ln + 2, pos, 10) or "0").strip())
                    except ValueError:
                        pass
        if "F11" in (screen.GetString(29, 69, 11) or ""):
            send_pf(screen, 11)
            if "YOU MAY NOT PAGE FORWARD AT THIS TIME" in (screen.GetString(31, 2, 60) or "").upper():
                break
        else:
            break
    send_pf(screen, 9)
    return f"{amt:.2f}"


# ---------------------------------------------------------------------------
# bypass_duplicate — mirrors ByPassDuplicate VBA
# ---------------------------------------------------------------------------

def bypass_duplicate(screen, claim_type: str, settings: dict):
    if get_screen_id(screen) != "CPS506.01":
        return
    send_pf(screen, 8)
    if claim_type == "UB":
        place_value(screen, "460", 2, 37)
    else:
        place_value(screen, "450", 2, 37)
    send_enter(screen)
    if settings.get("aply_631_inel", "N") == "Y":
        apply_631_inel(screen, claim_type, "631")
    if settings.get("aply_034_inel", "N") == "Y":
        apply_631_inel(screen, claim_type, "034")
    if claim_type == "UB":
        place_value(screen, "x", 29, 78)
    else:
        place_value(screen, "x", 29, 76)
    send_enter(screen)


# ---------------------------------------------------------------------------
# Collect Inel 700 — mirrors CollectInel700 VBA
# ---------------------------------------------------------------------------

def collect_inel_700(screen) -> dict:
    send_pf(screen, 8)
    place_value(screen, "408", 2, 37)
    send_enter(screen)
    idx = 0
    result = {}
    while True:
        for i in (6, 20):
            if (screen.GetString(i, 3, 4) or "").strip() == "INEL":
                idx += 1
                for j in range(10, 35, 12):
                    val = (screen.GetString(i, j, 3) or "").strip()
                    if val:
                        if val == "700":
                            result[idx] = "0"
                        break
        send_pf(screen, 11)
        if "YOU MAY NOT PAGE FORWARD" in (screen.GetString(31, 2, 60) or "").upper():
            break
    send_pf(screen, 8)
    place_value(screen, "450", 2, 37)
    send_enter(screen)
    return result


# ---------------------------------------------------------------------------
# Condition note helper — mirrors Add_Condition_Note VBA
# ---------------------------------------------------------------------------

def add_condition_note(screen, row: dict) -> bool:
    send_pf(screen, 8)
    place_value(screen, "910", 2, 37)
    send_enter(screen)
    place_value(screen, str(row.get("COND_NOTE", "") or ""), 7, 6)
    send_enter(screen)
    if get_screen_id(screen) == "CPS910.01":
        return False
    return True


def update_condition_afv(screen, row: dict) -> bool:
    send_pf(screen, 8)
    place_value(screen, "910", 2, 37)
    wait_ready(screen)
    send_enter(screen)
    place_value(screen, str(row.get("AFV", "") or "").strip(), 5, 68)
    wait_ready(screen)
    send_enter(screen)
    if get_screen_id(screen) == "CPS910.01":
        return False
    return True


# ---------------------------------------------------------------------------
# CSR note — mirrors PlaceNewCSRNote VBA
# ---------------------------------------------------------------------------

def place_new_csr_note(screen, row: dict, opt: str) -> str:
    """Returns status suffix string."""
    place_value(screen, "x", 29, 21)
    send_enter(screen)
    if (screen.GetString(1, 71, 10) or "").strip() != "BLX120.01":
        return " UNABLE TO REACH CPS110 SCREEN."
    if opt == "APPEND ON CURRENT NOTE":
        r = 6
        existing = (screen.GetString(6, 11, 60) or "").strip() + " " + (screen.GetString(7, 11, 60) or "").strip()
        note_text = existing + " " + str(row.get("NOTE_850", "") or "")
        remove_value(screen, 6, 11)
        remove_value(screen, 7, 11)
    else:  # 2ND LINE ONLY
        r = 7
        note_text = str(row.get("NOTE_850", "") or "")
    words = note_text.split()
    line = ""
    for word in words:
        candidate = (line + " " + word).strip()
        if len(candidate) > 60:
            place_value(screen, line.strip(), r, 11)
            line = word
            r += 1
        else:
            line = candidate
    if line.strip():
        place_value(screen, line.strip(), r, 11)
    send_enter(screen)
    send_pf(screen, 8)
    place_value(screen, "850", 2, 37)
    send_enter(screen)
    return " CSR NOTE UPDATED."


# ---------------------------------------------------------------------------
# Apply Discount After Switch (flip modifier) — mirrors APPLY_DISCOUNT_AFTER_SWITCH VBA
# ---------------------------------------------------------------------------

def apply_discount_after_switch(screen, ln_no: str) -> str:
    send_pf(screen, 8)
    place_value(screen, "408", 2, 37)
    send_enter(screen)
    mrk = (screen.GetString(3, 2, 70) or "").strip()
    while True:
        for j in range(3, 18, 14):
            if (screen.GetString(j, 2, 3) or "").strip() == f"{int(ln_no):03d}":
                for k in range(10, 59, 12):
                    if (screen.GetString(j + 3, k, 3) or "").strip() == "908":
                        amt = (screen.GetString(j + 4, k - 7, 10) or "").strip()
                        send_pf(screen, 8)
                        place_value(screen, "450", 2, 37)
                        send_enter(screen)
                        return amt
        send_pf(screen, 11)
        new_mrk = (screen.GetString(3, 2, 70) or "").strip()
        if new_mrk == mrk:
            break
        mrk = new_mrk
    return ""
