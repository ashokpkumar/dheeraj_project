"""
HCFA (CPS450.01 / BLX2460.01) data entry — port of Modules_oHCFA.txt VBA.
Returns 1 on success, 0 on skip/error (mirrors the VBA integer return).
The row dict uses column names from the Excel grid (row 13).
"""

from .utils import (
    get_screen_id, place_value, remove_value,
    send_enter, send_pf, wait_ready,
    data_entry_in_cps506, apply_631_inel,
    check_inel_code, bypass_duplicate,
    is_fully_paid, total_amt_858, plan_id_update,
    collect_inel_700, apply_discount_after_switch,
)


def hcfa_data_entry(screen, row: dict, settings: dict, codes: dict, status_parts: list) -> int:
    """
    Mirrors HCFA_Data_Entry VBA function.
    Mutates status_parts list to accumulate status messages.
    Returns 1 (continue) or 0 (skip row).
    """
    grid_price   = codes.get("grid_price", {})
    dx_codes     = codes.get("dx_codes", {})
    lab_codes    = codes.get("lab_codes", {})
    rule_lab_codes = codes.get("lab_cpt_codes_by_rule", {}).get(row.get("RULE_KEY", ""), {})
    mod_codes    = codes.get("mod_codes", {})
    dn_excptn    = codes.get("dnl_inel_exceptions", {})
    disc_after   = codes.get("apply_disc_after_dnl", {})
    rem_disc     = codes.get("rem_disc_amt", {})
    possible_hcr = codes.get("possible_hcr", {})
    dny_by_cpt   = codes.get("dny_by_cpt", {})
    rej_inel     = codes.get("rejected_inel", {})
    cpt_full_pd  = codes.get("cpt_codes_full_pd", {})

    screen_obj = screen  # alias

    # --- CPS450.01 entry ---
    new_pos = str(row.get("NEW_POS", "") or "").strip()
    if new_pos:
        screen_obj.PutString(new_pos, 2, 6)
        wait_ready(screen_obj)

    if settings.get("apply_uc", "Y") == "Y":
        screen_obj.PutString("X", 29, 69)
        wait_ready(screen_obj)

    new_ov_aj = str(row.get("NEW_OV_AJ", "") or "").strip()
    if new_ov_aj:
        screen_obj.PutString(new_ov_aj, 26, 37)
        wait_ready(screen_obj)

    # Other insurance section
    for o in range(20, 24):
        if (screen_obj.GetString(o, 12, 17) or "").strip():
            if settings.get("rem_oi_elig_amt", "N") == "Y":
                remove_value(screen_obj, o, 4)
                remove_value(screen_obj, o, 16)
                remove_value(screen_obj, o, 28)

    edit_msg = ""
    q = 9
    l = 15
    my_msg = ""

    for p in range(5, 12, 2):
        if not (screen_obj.GetString(p, 4, 6) or "").strip():
            q -= 1; l -= 1
            continue

        # FAIE Adjust Inel
        if settings.get("faie_adj_inel", "N") == "Y":
            if (screen_obj.GetString(p + q, 14, 3) or "").strip() == "908":
                faie_cd = str(row.get("FAIE_INEL_CD", "") or "").strip()
                if faie_cd:
                    place_value(screen_obj, (screen_obj.GetString(p + q, 2, 12) or "").strip(), p + q, 18)
                    place_value(screen_obj, f"{int(faie_cd):03d}", p + q, 30)
                    remove_value(screen_obj, p + q, 2)

        # Remove Discount Amount
        rem_disc_setting = settings.get("rem_disc_amt_flag", "N")
        if rem_disc_setting == "Y":
            if (screen_obj.GetString(p + q, 14, 3) or "").strip() in rem_disc:
                oi_type = (screen_obj.GetString(p + l, 28, 1) or "").strip().upper()
                if oi_type in ("X", "A"):
                    remove_value(screen_obj, p + q, 2)
        elif rem_disc_setting == "Y-DONT READ OITYPE":
            if (screen_obj.GetString(p + q, 14, 3) or "").strip() in rem_disc:
                remove_value(screen_obj, p + q, 2)

        if settings.get("del_bn", "N") == "Y":
            remove_value(screen_obj, p + l, 31)
            remove_value(screen_obj, p + l, 36)

        if settings.get("inel_switch", "N") == "Y":
            if (screen_obj.GetString(14, 14, 3) or "").strip() == "908":
                place_value(screen_obj, str(row.get("INEL_SWITCH_VAL", "") or "").strip(), 14, 14)

        if settings.get("bond_clinic", "N") == "Y":
            _apply_bond_clinic(screen_obj, row, p, q)

        if settings.get("flip_mod", "N") == "Y":
            _switch_mod(screen_obj, p, q, row, settings)

        # Apply 001
        apply_001 = settings.get("apply_001", "N/A")
        new_inel_cd = str(row.get("NEW_INEL_CD", "") or "").strip()
        if apply_001 == "1 ONLY" and p + q == 14:
            if (screen_obj.GetString(p + q, 2, 11) or "").strip():
                remove_value(screen_obj, p + q, 14); place_value(screen_obj, "001", p + q, 14)
            if (screen_obj.GetString(p + q, 18, 11) or "").strip():
                remove_value(screen_obj, p + q, 30); place_value(screen_obj, "001", p + q, 30)
        elif apply_001 == "ALL LINES":
            if (screen_obj.GetString(p + q, 2, 11) or "").strip():
                remove_value(screen_obj, p + q, 14); place_value(screen_obj, "001", p + q, 14)
            if (screen_obj.GetString(p + q, 18, 11) or "").strip():
                remove_value(screen_obj, p + q, 30); place_value(screen_obj, "001", p + q, 30)
        elif apply_001 == "N/A":
            remove_inel = settings.get("remove_inel_amt_cd", "N/A")
            if remove_inel == "N/A":
                if (screen_obj.GetString(p + q, 2, 11) or "").strip():
                    if (screen_obj.GetString(p + q, 14, 3) or "").strip() == "001":
                        edit_msg = "001 FOUND"
                        status_parts.append(edit_msg)
                        return 0
                if (screen_obj.GetString(p + q, 18, 11) or "").strip():
                    if (screen_obj.GetString(p + q, 30, 3) or "").strip() == "001":
                        edit_msg = "001 FOUND"
                        status_parts.append(edit_msg)
                        return 0

        # 2nd inel 001
        if settings.get("2nd_inel_001", "N") == "Y":
            if new_inel_cd == "":
                pass
            elif new_inel_cd == "001":
                place_value(screen_obj, "001", p + q, 30)
            else:
                place_value(screen_obj, "0.00", p + q, 18)
                place_value(screen_obj, new_inel_cd, p + q, 30)

        # Remove Inel Amt/Cd
        remove_inel = settings.get("remove_inel_amt_cd", "N/A")
        inel_cd_to_rmv = settings.get("inel_cd_to_rmv", "")
        aply_spcfc = settings.get("aply_inel_cd_spcfc_rmval", "N")
        if remove_inel == "INEL/CD1":
            if aply_spcfc == "Y":
                if (screen_obj.GetString(p + q, 14, 3) or "").strip() == inel_cd_to_rmv:
                    remove_value(screen_obj, p + q, 2); remove_value(screen_obj, p + q, 14)
            else:
                remove_value(screen_obj, p + q, 2); remove_value(screen_obj, p + q, 14)
        elif remove_inel == "INEL/CD2":
            if aply_spcfc == "Y":
                if (screen_obj.GetString(p + q, 30, 3) or "").strip() == inel_cd_to_rmv:
                    remove_value(screen_obj, p + q, 18); remove_value(screen_obj, p + q, 30)
            else:
                remove_value(screen_obj, p + q, 18); remove_value(screen_obj, p + q, 30)
        elif remove_inel == "INEL/CD ALL":
            if aply_spcfc == "Y":
                if (screen_obj.GetString(p + q, 14, 3) or "").strip() == inel_cd_to_rmv:
                    remove_value(screen_obj, p + q, 2); remove_value(screen_obj, p + q, 14)
                if (screen_obj.GetString(p + q, 30, 3) or "").strip() == inel_cd_to_rmv:
                    remove_value(screen_obj, p + q, 18); remove_value(screen_obj, p + q, 30)
            else:
                remove_value(screen_obj, p + q, 2); remove_value(screen_obj, p + q, 14)
                remove_value(screen_obj, p + q, 18); remove_value(screen_obj, p + q, 30)
        elif remove_inel == "SPECIFIC":
            specific_inels = [x.strip() for x in str(row.get("REMV_SPCFC_INEL", "") or "").split(";") if x.strip()]
            for y in (14, 30):
                for x in range(14, 18):
                    if (screen_obj.GetString(x, y, 3) or "").strip() in specific_inels:
                        remove_value(screen_obj, x, y)
                        remove_value(screen_obj, x, y - 12)

        # Deny Claim HCFA
        if settings.get("deny_clm", "N") == "Y":
            denial_code = settings.get("denial_code", "")
            inel_cd1 = (screen_obj.GetString(p + q, 14, 3) or "").strip()
            if inel_cd1 not in dn_excptn:
                if settings.get("dis_aft_dnl", "N") == "Y":
                    if (screen_obj.GetString(p + q, 18, 11) or "").strip():
                        status_parts.append("APPLY DISCOUNT AFTER DENIAL:INELCD2 PRESENT.")
                        return 0
                    if inel_cd1 in disc_after:
                        inel_code = settings.get("inel_code", "")
                        if inel_code and dny_by_cpt:
                            cpt = (screen_obj.GetString(p, 41, 5) or "").strip()
                            if cpt in dny_by_cpt:
                                inel1_amt_str = (screen_obj.GetString(p + q, 2, 11) or "").strip()
                                chrg = float((screen_obj.GetString(p, 21, 11) or "0").strip())
                                if inel1_amt_str:
                                    calc = round(chrg - float(inel1_amt_str), 2)
                                    if calc != 0:
                                        place_value(screen_obj, f"{calc:.2f}", p + q, 18)
                                        place_value(screen_obj, f"{int(inel_code):03d}", p + q, 30)
                                    else:
                                        bu = float((screen_obj.GetString(p, 33, 5) or "0").strip())
                                        place_value(screen_obj, str(bu), p, 74)
                                        place_value(screen_obj, str(bu), p, 78)
                                else:
                                    place_value(screen_obj, str(chrg), p + q, 18)
                                    place_value(screen_obj, f"{int(inel_code):03d}", p + q, 30)
                        else:
                            inel1_amt_str = (screen_obj.GetString(p + q, 2, 11) or "").strip()
                            chrg = float((screen_obj.GetString(p, 21, 11) or "0").strip())
                            if inel1_amt_str:
                                calc = round(chrg - float(inel1_amt_str), 2)
                                if calc != 0:
                                    place_value(screen_obj, f"{calc:.2f}", p + q, 18)
                                    place_value(screen_obj, f"{int(denial_code):03d}", p + q, 30)
                                else:
                                    bu = float((screen_obj.GetString(p, 33, 5) or "0").strip())
                                    place_value(screen_obj, str(bu), p, 74)
                                    place_value(screen_obj, str(bu), p, 78)
                            else:
                                place_value(screen_obj, str(chrg), p + q, 18)
                                place_value(screen_obj, f"{int(denial_code):03d}", p + q, 30)
                    else:
                        if not (screen_obj.GetString(p + q, 14, 3) or "").strip():
                            chrg = (screen_obj.GetString(p, 21, 11) or "0").strip()
                            place_value(screen_obj, str(float(chrg)), p + q, 2)
                            place_value(screen_obj, f"{int(denial_code):03d}", p + q, 14)
                    inel_cd_now = (screen_obj.GetString(p + q, 14, 3) or "").strip()
                    if inel_cd_now == "183":
                        place_value(screen_obj, "0", p + q, 50)
                else:
                    remove_value(screen_obj, p + q, 2); remove_value(screen_obj, p + q, 14)
                    chrg = (screen_obj.GetString(p, 21, 11) or "0").strip()
                    place_value(screen_obj, str(float(chrg)), p + q, 2)
                    place_value(screen_obj, f"{int(denial_code):03d}", p + q, 14)
                    if (screen_obj.GetString(p + q, 18, 11) or "").strip():
                        remove_value(screen_obj, p + q, 18); remove_value(screen_obj, p + q, 30)
            else:
                if not (screen_obj.GetString(p + q, 2, 11) or "").strip():
                    chrg = (screen_obj.GetString(p, 21, 11) or "0").strip()
                    place_value(screen_obj, str(float(chrg)), p + q, 2)
                    place_value(screen_obj, f"{int(settings.get('denial_code','0')):03d}", p + q, 14)

        # Apply Denial After Medicare
        if settings.get("aply_dnl_aft_medcr", "N") == "Y":
            oi_elig = (screen_obj.GetString(p + q + 6, 4, 11) or "").strip()
            if oi_elig:
                place_value(screen_obj, oi_elig, p + q, 18)
                place_value(screen_obj, f"{int(settings.get('denial_code','0')):03d}", p + q, 30)

        if settings.get("remove_ap", "N") == "Y":
            remove_value(screen_obj, p + l, 68)
        if settings.get("rem_code_set", "N") == "Y":
            remove_value(screen_obj, p, 39)
        if settings.get("chnge_dx_cd", "N") == "Y":
            remove_value(screen_obj, p + 1, 70)
            place_value(screen_obj, str(row.get("DX_CD", "") or "").strip(), p + 1, 70)
        if settings.get("apply_bn_qty", "N") == "Y":
            remove_value(screen_obj, (p + q) + 6, 31)
            place_value(screen_obj, str(row.get("BN_CODE", "") or "").strip(), (p + q) + 6, 31)
            remove_value(screen_obj, (p + q) + 6, 36)
            place_value(screen_obj, str(row.get("BN_QTY", "") or "").strip(), (p + q) + 6, 36)

        # 1st AP Code
        ap1 = str(row.get("AP_CD_1ST", "") or "").strip()
        if settings.get("aply_two_ap_cd", "N") == "Y" and ap1:
            place_value(screen_obj, ap1, p + l, 68)

        # Modifier logic
        new_ap_cd = str(row.get("NEW_AP_CD", "") or "").strip()
        if settings.get("aply_modifr", "N") == "Y":
            mods = [(screen_obj.GetString(p, j, 3) or "").strip() for j in range(47, 60, 4)]
            if any(m in mod_codes for m in mods):
                remove_value(screen_obj, p + l, 68)
                place_value(screen_obj, new_ap_cd, p + l, 68)
        else:
            if new_ap_cd and lab_codes.get((screen_obj.GetString(p, 41, 5) or "").strip()):
                place_value(screen_obj, new_ap_cd, p + l, 68)
            if new_ap_cd and settings.get("apply_dx", "N") == "N" and settings.get("apply_lab", "N") == "N":
                place_value(screen_obj, new_ap_cd, p + l, 68)
            if settings.get("apply_lab", "N") == "Y":
                cpt_val = (screen_obj.GetString(p, 41, 5) or "").strip()
                if new_ap_cd and cpt_val in rule_lab_codes:
                    place_value(screen_obj, new_ap_cd, p + l, 68)
            dx_val = (screen_obj.GetString(p + 1, 70, 7) or "").strip()
            if dx_val and settings.get("apply_dx", "N") == "Y":
                if dx_val in dx_codes:
                    if (screen_obj.GetString(p, 18, 2) or "").strip() == "23":
                        if new_ap_cd:
                            place_value(screen_obj, new_ap_cd, p + l, 68)

        if settings.get("remv_prov_rate", "N") == "Y":
            for rr in range(14, 18):
                if (screen_obj.GetString(rr, 50, 11) or "").strip():
                    remove_value(screen_obj, rr, 50)

        if settings.get("remv_modifr", "N") == "Y":
            for i in range(5, 12, 2):
                for j in range(47, 60, 4):
                    cur_mod = (screen_obj.GetString(i, j, 3) or "").strip()
                    if cur_mod in mod_codes:
                        remove_value(screen_obj, i, j)

        if settings.get("dx_lab_rev", "N") == "Y":
            cpt_val = (screen_obj.GetString(p, 41, 5) or "").strip()
            dx_val = (screen_obj.GetString(p + 1, 70, 7) or "").strip()
            if cpt_val in lab_codes and dx_val in dx_codes:
                place_value(screen_obj, "#", p + l, 68)

        # New OI Elig/Paid
        _apply_new_oi_elig_pd(screen_obj, row, p, l, settings.get("new_oi_elig_pd", "N/A"))
        # New OI Indicator
        _apply_new_oi_indicator(screen_obj, row, p, l, settings.get("new_oi_indctr", "N/A"))

        # Grid price check
        if settings.get("aply_grid_prc", "N") == "Y":
            if (screen_obj.GetString(p, 4, 6) or "").strip():
                inel_line = {5: 14, 7: 15, 9: 16, 11: 17}.get(p)
                if inel_line:
                    chg = float((screen_obj.GetString(p, 21, 11) or "0").strip())
                    cpt = (screen_obj.GetString(p, 41, 6) or "").strip()
                    allow_amt = grid_price.get(cpt, 0)
                    if chg > allow_amt and allow_amt != 0:
                        remove_value(screen_obj, inel_line, 2)
                        place_value(screen_obj, f"{chg - allow_amt:.2f}", inel_line, 2)
                        remove_value(screen_obj, inel_line, 14)
                        place_value(screen_obj, "997", inel_line, 14)

        # Deny S9451
        if settings.get("dny_s9451", "Y") == "Y":
            if (screen_obj.GetString(p, 41, 5) or "").strip() == "S9451":
                place_value(screen_obj, (screen_obj.GetString(p, 21, 11) or "").strip(), p + q, 2)
                place_value(screen_obj, "947", p + q, 14)

        # Identify possible HCR
        if settings.get("id_hcr", "Y") == "Y":
            if (screen_obj.GetString(p, 41, 5) or "").strip() in possible_hcr:
                if (screen_obj.GetString(p + q, 14, 3) or "").strip() in ("947", "200", "750", "751", "800", "804"):
                    status_parts.append("POSSIBLE HCR")
                    return 0

        if settings.get("rem_tu", "N") == "Y":
            remove_value(screen_obj, p, 63)

        # Add Time Units
        if settings.get("add_time", "N") == "Y":
            tu_str = str(row.get("TIME_UNITS", "") or "").strip()
            tu_status = str(row.get("TIME_UNIT_STATUS", "") or "").strip()
            if tu_str and not tu_status:
                try:
                    add_time = int(tu_str)
                    old_t_str = (screen_obj.GetString(p, 63, 5) or "").strip()
                    old_time = int(old_t_str) if old_t_str else 0
                    new_time = add_time + old_time
                    line_label = {5: "Line 1: ", 7: "Line 2: ", 9: "Line 3: ", 11: "Line 4: "}.get(p, "")
                    if new_time < 100:
                        remove_value(screen_obj, p, 63)
                        place_value(screen_obj, str(new_time), p, 63)
                        msg = f"{line_label}TIME updated from {old_time} to {new_time}."
                        my_msg = (my_msg + "\n" + msg).strip() if my_msg else msg
                    else:
                        msg = f"{line_label}TIME will exceed 99, no action done."
                        my_msg = (my_msg + "\n" + msg).strip() if my_msg else msg
                except ValueError:
                    pass
                row["TIME_UNIT_STATUS"] = my_msg

        q -= 1; l -= 1

    if settings.get("aply_631_inel", "N") == "Y":
        apply_631_inel(screen_obj, "HCFA", "631")
    if settings.get("aply_034_inel", "N") == "Y":
        apply_631_inel(screen_obj, "HCFA", "034")
    if settings.get("remove_prv", "N") == "Y":
        remove_value(screen_obj, 26, 9)
    new_prv = str(row.get("NEW_PRV_CD", "") or "").strip()
    if new_prv:
        place_value(screen_obj, new_prv, 26, 9)

    send_enter(screen_obj)

    # EDIT ERROR handling
    if "EDIT ERROR" in (screen_obj.GetString(30, 1, 20) or "").upper():
        if (screen_obj.GetString(24, 2, 4) or "").strip() == "MPIN":
            remove_value(screen_obj, 24, 7)
        if (screen_obj.GetString(22, 29, 4) or "").strip() == "MPIN":
            remove_value(screen_obj, 22, 34)
        send_enter(screen_obj)

    # CPS445.01 (duplicate screen)
    if get_screen_id(screen_obj) == "CPS445.01":
        if settings.get("aply_dpsv", "Y") != "N":
            send_enter(screen_obj)
            place_value(screen_obj, "x", 29, 76)
            send_enter(screen_obj)
        else:
            num_str = (screen_obj.GetString(17, 66, 11) or "").strip()
            status_parts.append("POSSIBLE DUP" if num_str.replace(".", "").isdigit() else (screen_obj.GetString(17, 58, 20) or "").strip())
            return 0

    edit_msg = (screen_obj.GetString(31, 2, 78) or "").strip()

    # Calc charge mismatch
    if "1432-CALC CHRG NOT EQUAL TO TOTAL" in edit_msg:
        if settings.get("aply_dnl_aft_medcr", "N") == "Y":
            for p in range(20, 24):
                oi_elig = (screen_obj.GetString(p, 4, 11) or "").strip()
                oi_pd = (screen_obj.GetString(p, 16, 11) or "").strip()
                if oi_elig and oi_pd:
                    place_value(screen_obj, str(round(float(oi_elig) - float(oi_pd), 2)), p - 6, 18)
                    place_value(screen_obj, f"{int(settings.get('denial_code','0')):03d}", p - 6, 30)
        else:
            for r in (5, 7, 9, 11):
                place_value(screen_obj, "30", r, 18)
            place_value(screen_obj, "x", 29, 69)
        send_enter(screen_obj)
        if get_screen_id(screen_obj) == "CPS450.01":
            status_parts.append((screen_obj.GetString(31, 2, 60) or "").strip())
            return 0

    # BN code edits
    edit_msg, e_msgs = _handle_bn_edits_hcfa(screen_obj, row, settings, edit_msg)
    if edit_msg and "FOR BN" not in edit_msg:
        pass  # continue

    # DX exception
    if settings.get("aply_dx_excptn", "N") == "Y":
        edit_msg = _apply_dx_exception_hcfa(screen_obj, edit_msg)

    # POS/TOS
    edit_msg = (screen_obj.GetString(31, 2, 78) or "").strip()
    if any(x in edit_msg for x in ("1235-INVALID POS/TOS", "1256-OLD", "SAD 02   100", "SAD")):
        hcfa_tos_entry(screen_obj, str(row.get("NEW_TOS", "") or "").strip(), edit_msg, row)

    # Surprise bill
    edit_msg = (screen_obj.GetString(31, 2, 78) or "").strip()
    if "SURP BILL" in edit_msg or "SURPRISE BILL" in edit_msg:
        prv = (screen_obj.GetString(26, 9, 1) or "").strip().upper()
        if prv in ("E", "G", "Y"):
            place_value(screen_obj, "}", 26, 9)
            send_enter(screen_obj)

    # --- CPS506 screen ---
    if get_screen_id(screen_obj) != "CPS506.01":
        edit_msg = (screen_obj.GetString(31, 2, 78) or "").strip()
        if "SAF" in edit_msg:
            place_value(screen_obj, "SAF", 5, 31)
            send_enter(screen_obj)
            if get_screen_id(screen_obj) == "CPS506.01":
                pass
            else:
                status_parts.append(edit_msg + " " + e_msgs)
                return 0
        else:
            status_parts.append(edit_msg + " " + e_msgs)
            return 0

    # Payee check
    if (screen_obj.GetString(7, 8, 1) or "").strip() == "1" and str(settings.get("payee", "0")) == "0":
        status_parts.append("CHANGE PAYEE TO 1")
        return 0

    # Update OC for 700
    if settings.get("updt_oc_for_700", "N") == "Y":
        inel700 = collect_inel_700(screen_obj)
        for slot, key in ((5, 1), (7, 2), (9, 3), (11, 4)):
            val = "00010" if inel700.get(key) is not None else (screen_obj.GetString(slot, 33, 5) or "").strip()
            place_value(screen_obj, val, slot, 33)
        place_value(screen_obj, "x", 29, 69)
        send_enter(screen_obj)
        if get_screen_id(screen_obj) == "CPS445.01":
            if settings.get("aply_dpsv", "Y") != "N":
                send_enter(screen_obj)
                place_value(screen_obj, "x", 29, 76)
                send_enter(screen_obj)
            else:
                status_parts.append("POSSIBLE DUP")
                return 0
        if get_screen_id(screen_obj) != "CPS506.01":
            return 0

    # Validate Amt Pd
    if settings.get("vld_amt_pd", "N") == "Y":
        paid, msg = is_fully_paid(screen_obj, "InelCodes", rej_inel, cpt_full_pd)
        if not paid:
            status_parts.append(msg or "NOT PROCESSED. NOT 100% FULLY PD.")
            return 0
    if settings.get("vld_amt_pd_by_cpt", "N") == "Y":
        paid, msg = is_fully_paid(screen_obj, "CPTCodes", rej_inel, cpt_full_pd)
        if not paid:
            status_parts.append(msg or "NOT PROCESSED. NOT 100% FULLY PD.")
            return 0

    # 858 Amt Inquiry
    if settings.get("amt_858_inq", "N") == "Y":
        existing = str(row.get("AMT_858_TOTAL", "") or "").strip()
        existing_val = float(existing) if existing else 0.0
        row["AMT_858_TOTAL"] = f"{existing_val + float(total_amt_858(screen_obj)):.2f}"
        return 1

    # Two AP codes
    if settings.get("aply_two_ap_cd", "N") == "Y" and str(row.get("AP_CD_2ND", "") or "").strip():
        _hcfa_ap_code_entry(screen_obj, row)

    # Update HIC
    if settings.get("updt_hic", "N") == "Y":
        if str(row.get("SEQ_NO", "") or "").strip() and str(row.get("NEW_PLAN_ID", "") or "").strip():
            if not str(row.get("HIC_STATUS", "") or "").strip():
                row["HIC_STATUS"] = plan_id_update(screen_obj, row)

    # 631/034 Inel bypass
    if settings.get("aply_631_inel", "N") == "Y":
        bypass_duplicate(screen_obj, "HCFA", settings)
    if settings.get("aply_034_inel", "N") == "Y":
        bypass_duplicate(screen_obj, "HCFA", settings)

    # Check Inel
    if settings.get("chk_inel", "N") == "Y":
        found, codes_found = check_inel_code(screen_obj, settings.get("ck_inel", {}))
        if found:
            status_parts.append(f"CHECK INEL CODE:{codes_found}")
            return 0

    data_entry_in_cps506(screen_obj, row, settings)
    send_enter(screen_obj)

    # SAF check after release
    edit_msg = (screen_obj.GetString(31, 2, 78) or "").strip()
    if "SAF" in edit_msg:
        place_value(screen_obj, "SAF", 5, 31)
        send_enter(screen_obj)
    if (screen_obj.GetString(31, 12, 60) or "").strip() == "CRL 37   PROMPT PAY - RLS TYPE R REQUIRED":
        place_value(screen_obj, "R", 3, 39)
        send_enter(screen_obj)
    if (screen_obj.GetString(31, 12, 60) or "").strip() == "CRL 36   281136  DENIAL RELEASE CODE REQUIRED":
        place_value(screen_obj, "71", 3, 13)
        place_value(screen_obj, "Y", 3, 39)
        send_enter(screen_obj)

    # Duplicate inel codes
    if (screen_obj.GetString(31, 12, 60) or "").strip() == "CRL 95   281035DUPLICATE INEL. CODES FOR SAME SERVICE":
        send_pf(screen_obj, 8)
        place_value(screen_obj, "450", 2, 37)
        send_enter(screen_obj)
        for i in range(14, 18):
            if (screen_obj.GetString(i, 14, 3) or "").strip() == "908":
                if not (screen_obj.GetString(i, 2, 11) or "").strip():
                    remove_value(screen_obj, i, 14)
        send_enter(screen_obj)
        if get_screen_id(screen_obj) == "CPS506.01":
            status_parts.append((screen_obj.GetString(31, 2, 60) or "").strip())
            return 0
        data_entry_in_cps506(screen_obj, row, settings)
        send_enter(screen_obj)

    screen_code = (screen_obj.GetString(1, 74, 3) or "").strip()
    if screen_code == "115":
        status_parts.append(edit_msg)
        return 0
    if screen_code == "112":
        status_parts.append("Released.")
        return 1
    else:
        status_parts.append("Not Released. " + (screen_obj.GetString(31, 12, 60) or "").strip().replace("  ", " "))
        if (screen_obj.GetString(1, 74, 3) or "").strip() == "114":
            status_parts.append("Duplicate Claim")
        return 0


# ---------------------------------------------------------------------------
# HCFA TOS Entry
# ---------------------------------------------------------------------------

def hcfa_tos_entry(screen, new_tos: str, edit_msg: str, row: dict):
    sad_line = edit_msg[5:6] if len(edit_msg) > 5 else ""
    tos_rows = {
        "1": ([5, 7, 9, 11], 5),
        "2": ([7, 5, 9, 11], 7),
        "3": ([9, 5, 7, 11], 9),
        "4": ([11, 5, 7, 9], 11),
    }
    primary_row = tos_rows.get(sad_line, ([], None))[1]
    others = tos_rows.get(sad_line, ([], None))[0][1:]
    if primary_row:
        place_value(screen, new_tos, primary_row, 18)
        for rr in others:
            v = (screen.GetString(rr, 22, 10) or "").strip()
            if v in (".00", ".01") and v:
                place_value(screen, new_tos, rr, 18)

    old_inel = str(row.get("OLD_INEL_CD", "") or "").strip()
    new_inel = str(row.get("NEW_INEL_CD", "") or "").strip()
    for rr in range(14, 18):
        if (screen.GetString(rr, 14, 3) or "").strip() == old_inel:
            remove_value(screen, rr, 14)
            if new_inel:
                place_value(screen, new_inel, rr, 14)

    place_value(screen, "x", 29, 69)
    send_enter(screen)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_new_oi_elig_pd(screen, row, p, l, setting):
    elig = str(row.get("NEW_OI_ELIG", "") or "").strip()
    pd_val = str(row.get("NEW_OI_PD", "") or "").strip()
    line_map = {"1ST LINE": 20, "2ND LINE": 21, "3RD LINE": 22, "4TH LINE": 23}
    if setting == "N/A":
        return
    if setting == "ALL LINES":
        if elig: remove_value(screen, p + l, 4); place_value(screen, elig, p + l, 4)
        if pd_val: remove_value(screen, p + l, 16); place_value(screen, pd_val, p + l, 16)
    elif setting in line_map:
        rr = line_map[setting]
        if elig: remove_value(screen, rr, 4); place_value(screen, elig, rr, 4)
        if pd_val: remove_value(screen, rr, 16); place_value(screen, pd_val, rr, 16)


def _apply_new_oi_indicator(screen, row, p, l, setting):
    ind = str(row.get("NEW_OI_IND", "") or "").strip()
    line_map = {"1ST LINE": 20, "2ND LINE": 21, "3RD LINE": 22, "4TH LINE": 23}
    if setting == "N/A" or not ind:
        return
    if setting == "ALL LINES":
        remove_value(screen, p + l, 28); place_value(screen, ind, p + l, 28)
    elif setting in line_map:
        rr = line_map[setting]
        remove_value(screen, rr, 28); place_value(screen, ind, rr, 28)


def _handle_bn_edits_hcfa(screen, row, settings, edit_msg):
    e_msgs = ""
    while "FOR BN" in (edit_msg or ""):
        e_msgs += " " + edit_msg
        s_bn = edit_msg[edit_msg.index(":") + 1: edit_msg.index(":") + 4].strip() if ":" in edit_msg else ""
        sad = edit_msg[:6]
        line_row = {"SAD 01": 20, "SAD 02": 21, "SAD 03": 22, "SAD 04": 23}.get(sad)
        inel_row = {"SAD 01": 14, "SAD 02": 15, "SAD 03": 16, "SAD 04": 17}.get(sad)
        if line_row and s_bn:
            place_value(screen, s_bn, line_row, 31)
            bn_qty = str(row.get("BN_QTY", "") or "").strip()
            if bn_qty:
                place_value(screen, bn_qty, line_row, 36)
            if settings.get("apply_bn_thold", "N") == "Y":
                if inel_row and (screen.GetString(inel_row, 14, 4) or "").strip() == "908":
                    svc_line = {20: 5, 21: 7, 22: 9, 23: 11}.get(line_row, 5)
                    calc = float((screen.GetString(svc_line, 21, 11) or "0").strip()) - float((screen.GetString(inel_row, 2, 11) or "0").strip())
                    place_value(screen, f"{calc:.2f}", line_row, 36)
                else:
                    edit_msg = "MANUAL BN AMT NEEDS TO BE ENTERED."
                    return edit_msg, e_msgs
        send_enter(screen)
        prev = edit_msg
        edit_msg = (screen.GetString(31, 2, 78) or "").strip()
        if edit_msg == prev:
            return edit_msg, e_msgs
        e_msgs += " " + (screen.GetString(32, 2, 78) or "").strip()
    return edit_msg, e_msgs


def _apply_dx_exception_hcfa(screen, edit_msg):
    while "INVALID DX FOR SERVICE" in (edit_msg or ""):
        sad = edit_msg[:6]
        line_map = {"SAD 01": 6, "SAD 02": 8, "SAD 03": 10, "SAD 04": 12}
        rr = line_map.get(sad)
        if rr:
            place_value(screen, "E", rr, 78)
        send_enter(screen)
        edit_msg = (screen.GetString(31, 2, 78) or "").strip()
    return edit_msg


def _hcfa_ap_code_entry(screen, row):
    if (screen.GetString(1, 5, 6) or "").strip() == "506.01":
        send_pf(screen, 8)
        place_value(screen, "450", 2, 37)
        send_enter(screen)
        l = 15
        for i in range(5, 12, 2):
            if (screen.GetString(i, 4, 6) or "").strip():
                place_value(screen, str(row.get("AP_CD_2ND", "") or "").strip(), i + l, 68)
            l -= 1
    place_value(screen, "x", 29, 69)
    wait_ready(screen)
    send_enter(screen)


def _switch_mod(screen, p, q, row, settings):
    m = (screen.GetString(p, 47, 3) or "").strip()
    for i in range(47, 60, 4):
        mod = (screen.GetString(p, i, 3) or "").strip()
        if mod in ("P3", "P4", "P5"):
            place_value(screen, mod, p, 47)
            place_value(screen, m, p, i)
            if settings.get("apply_disc_aft_flip", "N") == "Y":
                ln_no = (screen.GetString(p, 2, 1) or "").strip()
                if settings.get("apply_uc", "Y") == "Y":
                    place_value(screen, "x", 29, 69)
                send_enter(screen)
                ds_amt = apply_discount_after_switch(screen, ln_no)
                if ds_amt:
                    place_value(screen, ds_amt, p + q, 2)
                    place_value(screen, "908", p + q, 14)
                    half = round(float((screen.GetString(p + 1, 4, 10) or "0").strip()) / 2, 2)
                    place_value(screen, str(half), p + q, 18)
                    place_value(screen, "930", p + q, 30)
                    place_value(screen, "x", 29, 69)
            break


def _apply_bond_clinic(screen, row, p, q):
    try:
        chrg = float((screen.GetString(p, 21, 11) or "0").strip())
        z = {5: 9, 7: 8, 9: 7, 11: 6}.get(p, 9)
        inel_amt = float((screen.GetString(p + z, 2, 11) or "0").strip())
        amt_ceiling = 10.0
        amt997 = chrg - inel_amt
        if chrg > amt_ceiling:
            amt997 = abs(amt997 - amt_ceiling)
            remove_value(screen, p + z, 18)
            place_value(screen, str(amt997), p + z, 18)
            remove_value(screen, p + z, 30)
            place_value(screen, "997", p + z, 30)
        else:
            if chrg > 10:
                remove_value(screen, p + z, 18)
                place_value(screen, str(amt997), p + z, 18)
                remove_value(screen, p + z, 30)
                place_value(screen, "997", p + z, 30)
    except (ValueError, TypeError):
        pass
