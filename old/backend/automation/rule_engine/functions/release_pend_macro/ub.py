"""
UB (BLX2460.01) data entry — port of Modules_0UB.txt VBA.
Returns 1 on success, 0 on skip/error.
"""

from .utils import (
    get_screen_id, place_value, remove_value,
    send_enter, send_pf, wait_ready,
    data_entry_in_cps506, apply_631_inel,
    check_inel_code, bypass_duplicate,
    is_fully_paid, total_amt_858, plan_id_update,
    collect_inel_700,
)


def ub_per_diem_process(screen, row: dict, settings: dict) -> int:
    """Mirrors UB_Per_Diem_Process VBA."""
    bln_rvw_svc = False

    for p in range(6, 10):
        if not (screen.GetString(p, 3, 4) or "").strip():
            continue
        _apply_new_oi_indicator_ub(screen, row, p, settings.get("new_oi_indctr", "N/A"))

    send_enter(screen)

    if settings.get("remv_prcrt_byps", "N") == "Y":
        msg31 = (screen.GetString(31, 1, 70) or "").strip()
        if "PC# NOT VALID FOR PATIENT" in msg31 or "8803" in msg31:
            remove_value(screen, 2, 12)
            place_value(screen, "RP", 2, 5)
            wait_ready(screen)
            send_enter(screen)

    place_value(screen, "60", 3, 13)
    place_value(screen, "N", 3, 39)
    place_value(screen, "O99", 3, 53)
    place_value(screen, "CF10", 4, 13)
    place_value(screen, "001", 4, 38)
    place_value(screen, "PER DIEM LINE", 4, 50)
    send_enter(screen)
    send_pf(screen, 8)
    place_value(screen, "460", 2, 37)
    send_enter(screen)

    while True:
        sid = get_screen_id(screen)
        if sid == "CPS445.01":
            bln_rvw_svc = True
            send_enter(screen)
        elif sid == "CPS450.01":
            send_enter(screen)
            if bln_rvw_svc:
                place_value(screen, "x", 29, 78)
                send_enter(screen)
        elif sid == "BLX2460.01":
            place_value(screen, str(row.get("NEW_POS", "") or "").strip(), 1, 26)
            place_value(screen, str(row.get("NEW_TOS", "") or "").strip(), 6, 14)
            place_value(screen, "0001", 6, 3)
            place_value(screen, (screen.GetString(2, 63, 6) or "").strip(), 6, 17)
            place_value(screen, "001", 6, 32)
            place_value(screen, str(row.get("T_BILL", "") or "").strip(), 6, 40)
            place_value(screen, str(row.get("T_DISC", "") or "").strip(), 12, 2)
            place_value(screen, str(row.get("NEW_INEL_CD", "") or "").strip(), 12, 14)
            send_enter(screen)
            if get_screen_id(screen) == "BLX2460.01":
                return 0
        elif sid == "CPS506.01":
            place_value(screen, "60", 3, 13)
            place_value(screen, "N", 3, 39)
            place_value(screen, "O99", 3, 53)
            place_value(screen, "CF10", 4, 13)
            place_value(screen, "001", 4, 38)
            place_value(screen, "PER DIEM CREATED", 4, 50)
            place_value(screen, str(settings.get("payee", "0")), 7, 8)
            send_enter(screen)
            if get_screen_id(screen) == "CPS506.01":
                return 0
            return 1
        else:
            break

    return 1


def ub_data_entry(screen, row: dict, settings: dict, codes: dict, status_parts: list) -> int:
    """Mirrors UB_Data_Entry VBA function."""
    grid_price   = codes.get("grid_price", {})
    lab_codes    = codes.get("lab_codes", {})
    rule_lab_codes = codes.get("lab_cpt_codes_by_rule", {}).get(row.get("RULE_KEY", ""), {})
    ub_rev_codes = codes.get("ub_rev_codes", {})
    dx_codes     = codes.get("dx_codes", {})
    mod_codes    = codes.get("mod_codes", {})
    dn_excptn    = codes.get("dnl_inel_exceptions", {})
    disc_after   = codes.get("apply_disc_after_dnl", {})
    rem_disc     = codes.get("rem_disc_amt", {})
    possible_hcr = codes.get("possible_hcr", {})
    dny_by_cpt   = codes.get("dny_by_cpt", {})
    rej_inel     = codes.get("rejected_inel", {})
    cpt_full_pd  = codes.get("cpt_codes_full_pd", {})

    if get_screen_id(screen) == "CPS450.01":
        send_enter(screen)

    new_pos = str(row.get("NEW_POS", "") or "").strip()
    if new_pos:
        screen.PutString(new_pos, 1, 26)
        wait_ready(screen)
    if settings.get("apply_uc", "Y") == "Y":
        screen.PutString("X", 29, 71)
        wait_ready(screen)
    new_ov_aj = str(row.get("NEW_OV_AJ", "") or "").strip()
    if new_ov_aj:
        screen.PutString(new_ov_aj, 27, 62)
        wait_ready(screen)

    for o in range(18, 22):
        if (screen.GetString(o, 12, 15) or "").strip():
            if settings.get("rem_oi_elig_amt", "N") == "Y":
                screen.MoveTo(o, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.MoveTo(o, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.MoveTo(o, 26); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        if settings.get("remv_adj_cd", "N") == "Y":
            screen.MoveTo(o, 28); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)

    new_oi_elig = str(row.get("NEW_OI_ELIG", "") or "").strip()
    new_oi_pd = str(row.get("NEW_OI_PD", "") or "").strip()
    if new_oi_elig:
        screen.PutString(new_oi_elig, 18, 2)
    if new_oi_pd:
        screen.PutString(new_oi_pd, 18, 14)

    z = 3
    l = 0
    l2 = 6  # for del_bn offset

    for p in range(6, 10):
        if not (screen.GetString(p, 3, 4) or "").strip():
            z += 10; l += 3
            continue

        # FAIE Adjust Inel
        if settings.get("faie_adj_inel", "N") == "Y":
            if (screen.GetString(p + 6, 14, 3) or "").strip() == "908":
                faie_cd = str(row.get("FAIE_INEL_CD", "") or "").strip()
                if faie_cd:
                    place_value(screen, (screen.GetString(p + 6, 2, 12) or "").strip(), p + 6, 18)
                    place_value(screen, f"{int(faie_cd):03d}", p + 6, 30)
                    remove_value(screen, p + 6, 2)

        rem_disc_setting = settings.get("rem_disc_amt_flag", "N")
        if rem_disc_setting == "Y":
            if (screen.GetString(p + 6, 14, 3) or "").strip() in rem_disc:
                oi_type = (screen.GetString(p + 12, 26, 1) or "").strip().upper()
                if oi_type in ("X", "A"):
                    remove_value(screen, p + 6, 2)
        elif rem_disc_setting == "Y-DONT READ OITYPE":
            if (screen.GetString(p + 6, 14, 3) or "").strip() in rem_disc:
                remove_value(screen, p + 6, 2)

        if settings.get("inel_switch", "N") == "Y":
            if (screen.GetString(12, 14, 3) or "").strip() == "908":
                place_value(screen, str(row.get("INEL_SWITCH_VAL", "") or "").strip(), 12, 14)

        if settings.get("rem_iu", "N") == "Y":
            remove_value(screen, p, 36)

        # Apply 001
        apply_001 = settings.get("apply_001", "N/A")
        new_inel_cd = str(row.get("NEW_INEL_CD", "") or "").strip()
        if apply_001 == "1 ONLY" and p + 6 == 12:
            screen.MoveTo(p + 6, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString("001", p + 6, 14); wait_ready(screen)
            if (screen.GetString(p + 6, 18, 11) or "").strip():
                screen.MoveTo(p + 6, 30); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.PutString("001", p + 6, 30); wait_ready(screen)
        elif apply_001 == "ALL LINES":
            screen.MoveTo(p + 6, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString("001", p + 6, 14); wait_ready(screen)
            if (screen.GetString(p + 6, 18, 11) or "").strip():
                screen.MoveTo(p + 6, 30); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.PutString("001", p + 6, 30); wait_ready(screen)
        elif apply_001 == "N/A":
            remove_inel = settings.get("remove_inel_amt_cd", "N/A")
            if remove_inel == "N/A":
                if (screen.GetString(p + 6, 2, 11) or "").strip():
                    if (screen.GetString(p + 6, 14, 3) or "").strip() == "001":
                        status_parts.append("001 FOUND")
                        return 0
                if (screen.GetString(p + 6, 18, 11) or "").strip():
                    if (screen.GetString(p + 6, 30, 3) or "").strip() == "001":
                        status_parts.append("001 FOUND")
                        return 0

        # Remove Inel Amt/Cd
        remove_inel = settings.get("remove_inel_amt_cd", "N/A")
        inel_cd_to_rmv = settings.get("inel_cd_to_rmv", "")
        aply_spcfc = settings.get("aply_inel_cd_spcfc_rmval", "N")
        if remove_inel == "INEL/CD1":
            if aply_spcfc == "Y":
                if (screen.GetString(p + 6, 14, 3) or "").strip() == inel_cd_to_rmv:
                    screen.MoveTo(p + 6, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                    screen.MoveTo(p + 6, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            else:
                screen.MoveTo(p + 6, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.MoveTo(p + 6, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        elif remove_inel == "INEL/CD2":
            if aply_spcfc == "Y":
                if (screen.GetString(p + 6, 30, 3) or "").strip() == inel_cd_to_rmv:
                    screen.MoveTo(p + 6, 18); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                    screen.MoveTo(p + 6, 30); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            else:
                screen.MoveTo(p + 6, 18); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.MoveTo(p + 6, 30); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        elif remove_inel == "INEL/CD ALL":
            if aply_spcfc == "Y":
                if (screen.GetString(p + 6, 14, 3) or "").strip() == inel_cd_to_rmv:
                    screen.MoveTo(p + 6, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                    screen.MoveTo(p + 6, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                if (screen.GetString(p + 6, 30, 3) or "").strip() == inel_cd_to_rmv:
                    screen.MoveTo(p + 6, 18); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                    screen.MoveTo(p + 6, 30); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            else:
                screen.MoveTo(p + 6, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.MoveTo(p + 6, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.MoveTo(p + 6, 18); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                screen.MoveTo(p + 6, 30); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        elif remove_inel == "SPECIFIC":
            specific_inels = [x.strip() for x in str(row.get("REMV_SPCFC_INEL", "") or "").split(";") if x.strip()]
            for y in (14, 30):
                for x in range(12, 16):
                    if (screen.GetString(x, y, 3) or "").strip() in specific_inels:
                        screen.MoveTo(x, y); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                        screen.MoveTo(x, y - 12); screen.SendKeys("<EraseEOF>"); wait_ready(screen)

        # Deny Claim UB
        if settings.get("deny_clm", "N") == "Y":
            denial_code = settings.get("denial_code", "")
            inel_cd1 = (screen.GetString(p + 6, 14, 3) or "").strip()
            if inel_cd1 not in dn_excptn:
                if settings.get("dis_aft_dnl", "N") == "Y":
                    if (screen.GetString(p + 6, 18, 11) or "").strip():
                        status_parts.append("APPLY DISCOUNT AFTER DENIAL:INELCD2 PRESENT.")
                        return 0
                    if inel_cd1 in disc_after:
                        inel_code = settings.get("inel_code", "")
                        if inel_code and dny_by_cpt:
                            cpt = (screen.GetString(p, 8, 5) or "").strip()
                            if cpt in dny_by_cpt:
                                inel1_str = (screen.GetString(p + 6, 2, 11) or "").strip()
                                chrg = float((screen.GetString(p, 40, 11) or "0").strip())
                                if inel1_str:
                                    calc = round(chrg - float(inel1_str), 2)
                                    if calc != 0:
                                        place_value(screen, f"{calc:.2f}", p + 6, 18)
                                        place_value(screen, f"{int(inel_code):03d}", p + 6, 30)
                                    else:
                                        bu = float((screen.GetString(p, 32, 3) or "0").strip())
                                        place_value(screen, str(bu), p, 36)
                                else:
                                    place_value(screen, str(chrg), p + 6, 18)
                                    place_value(screen, f"{int(inel_code):03d}", p + 6, 30)
                        else:
                            inel1_str = (screen.GetString(p + 6, 2, 11) or "").strip()
                            chrg = float((screen.GetString(p, 40, 11) or "0").strip())
                            if inel1_str:
                                calc = round(chrg - float(inel1_str), 2)
                                if calc != 0:
                                    place_value(screen, f"{calc:.2f}", p + 6, 18)
                                    place_value(screen, f"{int(denial_code):03d}", p + 6, 30)
                                else:
                                    bu = float((screen.GetString(p, 32, 3) or "0").strip())
                                    place_value(screen, str(bu), p, 36)
                            else:
                                place_value(screen, str(chrg), p + 6, 18)
                                place_value(screen, f"{int(denial_code):03d}", p + 6, 30)
                    else:
                        if not (screen.GetString(p + 6, 14, 3) or "").strip():
                            chrg = (screen.GetString(p, 40, 11) or "0").strip()
                            place_value(screen, str(float(chrg)), p + 6, 2)
                            place_value(screen, f"{int(denial_code):03d}", p + 6, 14)
                    if (screen.GetString(p + 6, 14, 3) or "").strip() == "183":
                        place_value(screen, "0", p + 6, 50)
                else:
                    screen.MoveTo(p + 6, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                    screen.MoveTo(p + 6, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                    chrg = (screen.GetString(p, 40, 11) or "0").strip()
                    screen.PutString(str(float(chrg)), p + 6, 2); wait_ready(screen)
                    screen.PutString(f"{int(denial_code):03d}", p + 6, 14); wait_ready(screen)
                    if (screen.GetString(p + 6, 18, 11) or "").strip():
                        screen.MoveTo(p + 6, 18); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
                        screen.MoveTo(p + 6, 30); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            else:
                if not (screen.GetString(p + 6, 2, 11) or "").strip():
                    chrg = (screen.GetString(p, 40, 11) or "0").strip()
                    place_value(screen, str(float(chrg)), p + 6, 2)
                    place_value(screen, f"{int(settings.get('denial_code','0')):03d}", p + 6, 14)

        if settings.get("aply_dnl_aft_medcr", "N") == "Y":
            oi_elig = (screen.GetString(p + 12, 2, 11) or "").strip()
            if oi_elig:
                place_value(screen, oi_elig, p + 6, 18)
                place_value(screen, f"{int(settings.get('denial_code','0')):03d}", p + 6, 30)

        if settings.get("remove_ap", "N") == "Y":
            screen.MoveTo(10, 54 + l); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        if settings.get("rem_code_set", "N") == "Y":
            screen.MoveTo(p, 24); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        if settings.get("chnge_dx_cd", "N") == "Y":
            screen.MoveTo(10, z); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString(str(row.get("DX_CD", "") or "").strip(), 10, z); wait_ready(screen)

        new_ap_cd = str(row.get("NEW_AP_CD", "") or "").strip()
        if settings.get("apply_dx", "N") == "Y" and new_ap_cd:
            if (screen.GetString(p, 8, 5) or "").strip() in lab_codes:
                screen.PutString(new_ap_cd, 10, 54 + l); wait_ready(screen)
        if settings.get("apply_dx", "N") == "N" and settings.get("apply_lab", "N") == "N":
            if new_ap_cd:
                screen.PutString(new_ap_cd, 10, 54 + l); wait_ready(screen)
        if settings.get("apply_dx", "N") == "N" and settings.get("apply_lab", "N") == "Y":
            cpt_val = (screen.GetString(p, 8, 5) or "").strip()
            if new_ap_cd and cpt_val in rule_lab_codes:
                screen.PutString(new_ap_cd, 10, 54 + l); wait_ready(screen)

        ap1 = str(row.get("AP_CD_1ST", "") or "").strip()
        if settings.get("aply_two_ap_cd", "N") == "Y" and ap1:
            screen.PutString(ap1, 10, 54 + l); wait_ready(screen)

        if settings.get("remv_prov_rate", "N") == "Y":
            for rr in range(12, 16):
                if (screen.GetString(rr, 50, 11) or "").strip():
                    screen.MoveTo(rr, 50); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)

        if settings.get("remv_modifr", "N") == "Y":
            for i in range(6, 10):
                for j in range(52, 65, 4):
                    cur_mod = (screen.GetString(i, j, 3) or "").strip()
                    if cur_mod in mod_codes:
                        screen.MoveTo(i, j); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)

        if settings.get("dx_lab_rev", "N") == "Y":
            rev_code = (screen.GetString(p, 3, 4) or "").strip()
            cpt_val = (screen.GetString(p, 8, 5) or "").strip()
            dx_val = (screen.GetString(10, z, 7) or "").strip()
            if (rev_code in ub_rev_codes and dx_val in dx_codes) or (cpt_val in lab_codes and dx_val in dx_codes):
                screen.PutString("#", 10, 54 + l); wait_ready(screen)

        # New OI Elig/Paid (UB per-line for ALL LINES)
        _apply_ub_oi_elig_pd(screen, row, p, settings.get("new_oi_elig_pd", "N/A"))
        _apply_new_oi_indicator_ub(screen, row, p, settings.get("new_oi_indctr", "N/A"))

        if settings.get("del_bn", "N") == "Y":
            remove_value(screen, p + l2, 43)
            remove_value(screen, p + l2, 48)

        # Deny S9451
        if settings.get("dny_s9451", "Y") == "Y":
            if (screen.GetString(p, 8, 5) or "").strip() == "S9451":
                place_value(screen, (screen.GetString(p, 39, 11) or "").strip(), p + 6, 2)
                place_value(screen, "947", p + 6, 14)

        # Identify possible HCR
        if settings.get("id_hcr", "Y") == "Y":
            if (screen.GetString(p, 8, 5) or "").strip() in possible_hcr:
                if (screen.GetString(p + 6, 14, 3) or "").strip() in ("947", "200", "750", "751", "800", "804"):
                    status_parts.append("POSSIBLE HCR")
                    return 0

        if settings.get("2nd_inel_001", "N") == "Y":
            new_inel_cd = str(row.get("NEW_INEL_CD", "") or "").strip()
            if new_inel_cd == "":
                pass
            elif new_inel_cd == "001":
                place_value(screen, "001", p + 6, 30)
            else:
                place_value(screen, "0.00", p + 6, 18)
                place_value(screen, new_inel_cd, p + 6, 30)

        # New OI Indicator per all lines (ALL LINES case handled in helper)
        z += 10; l += 3

    if settings.get("aply_631_inel", "N") == "Y":
        apply_631_inel(screen, "UB", "631")
    if settings.get("aply_034_inel", "N") == "Y":
        apply_631_inel(screen, "UB", "034")

    if settings.get("remove_prv", "N") == "Y":
        screen.MoveTo(22, 6); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
    new_prv = str(row.get("NEW_PRV_CD", "") or "").strip()
    if new_prv:
        screen.PutString(new_prv, 22, 6); wait_ready(screen)

    if settings.get("apply_bn_qty", "N") == "Y":
        for s in range(12, 16):
            screen.MoveTo(s + 6, 43); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString(str(row.get("BN_CODE", "") or "").strip(), s + 6, 43); wait_ready(screen)
            screen.MoveTo(s + 6, 48); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString(str(row.get("BN_QTY", "") or "").strip(), s + 6, 48); wait_ready(screen)

    send_enter(screen)

    # Edit error handling
    if "EDIT ERROR" in (screen.GetString(30, 1, 20) or "").upper():
        if screen.fieldattribute(4, 35) == "201":
            screen.MoveTo(4, 35); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        if screen.fieldattribute(4, 63) == "201":
            screen.MoveTo(4, 63); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        if (screen.GetString(24, 2, 4) or "").strip() == "MPIN":
            screen.MoveTo(24, 7); wait_ready(screen)
        if (screen.GetString(22, 29, 4) or "").strip() == "MPIN":
            screen.MoveTo(22, 34); wait_ready(screen)
        screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        screen.SendKeys("<ENTER>"); wait_ready(screen)

    if get_screen_id(screen) == "CPS445.01":
        if settings.get("aply_dpsv", "Y") != "N":
            send_enter(screen)
            if get_screen_id(screen) == "CPS450.01":
                send_pf(screen, 8)
                screen.PutString("460", 2, 37); wait_ready(screen)
                send_enter(screen)
            screen.PutString("x", 29, 78); wait_ready(screen)
            send_enter(screen)
        else:
            num_str = (screen.GetString(17, 66, 11) or "").strip()
            status_parts.append("POSSIBLE DUP" if num_str.replace(".", "").isdigit() else (screen.GetString(17, 58, 20) or "").strip())
            return 0

    edit_msg = (screen.GetString(31, 2, 78) or "").strip()
    if "1432-CALC CHRG NOT EQUAL TO TOTAL" in edit_msg:
        if settings.get("aply_dnl_aft_medcr", "N") == "Y":
            for p in range(18, 22):
                oi_elig = (screen.GetString(p, 2, 11) or "").strip()
                oi_pd = (screen.GetString(p, 14, 11) or "").strip()
                if oi_elig and oi_pd:
                    place_value(screen, str(round(float(oi_elig) - float(oi_pd), 2)), p - 6, 18)
                    place_value(screen, f"{int(settings.get('denial_code','0')):03d}", p - 6, 30)
        send_enter(screen)
        if get_screen_id(screen) == "BLX2460.01":
            status_parts.append((screen.GetString(31, 2, 60) or "").strip())
            return 0

    edit_msg = (screen.GetString(31, 2, 78) or "").strip()
    if "FOR BN" in edit_msg:
        for s in range(12, 16):
            if (screen.GetString(s, 14, 3) or "").strip():
                screen.PutString(str(row.get("BN_CODE", "") or "").strip(), s + 6, 43); wait_ready(screen)
        send_enter(screen)

    bln_sp = False
    while True:
        edit_msg = (screen.GetString(31, 2, 78) or "").strip()
        code_4 = edit_msg[9:13] if len(edit_msg) > 12 else ""
        if code_4 in ("8803", "8806", "8807"):
            screen.PutString("RP", 2, 5); wait_ready(screen)
            screen.MoveTo(2, 12); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            send_enter(screen)
            continue

        if "1237-SP REQUIRED" in edit_msg:
            sad = edit_msg[:6]
            sp_map = {
                "SAD 01": (6, 18, 30), "SAD 02": (7, 19, 30),
                "SAD 03": (8, 20, 30), "SAD 04": (9, 21, 30)
            }
            if sad in sp_map:
                svc_row, oi_row, oi_col = sp_map[sad]
                try:
                    sp_amt = f"{float((screen.GetString(svc_row, 40, 12) or '0').strip()) / float((screen.GetString(svc_row, 32, 3) or '1').strip()):.2f}"
                    screen.PutString(sp_amt, oi_row, oi_col); wait_ready(screen)
                except (ValueError, ZeroDivisionError):
                    pass
                send_enter(screen)
                bln_sp = True
                continue
        break

    if bln_sp and "PRVD OPI P&P" in (edit_msg or ""):
        sad = edit_msg[:6]
        inel_rows = {"SAD 01": 12, "SAD 02": 13, "SAD 03": 14, "SAD 04": 15}
        if sad in inel_rows:
            rr = inel_rows[sad]
            if not (screen.GetString(rr, 2, 11) or "").strip():
                screen.PutString("0.00", rr, 2); screen.PutString("908", rr, 14); wait_ready(screen)
                send_enter(screen)
            else:
                status_parts.append("INEL AMT PRESENT")
                return 0

    if settings.get("aply_dx_excptn", "N") == "Y":
        edit_msg = (screen.GetString(31, 2, 78) or "").strip()
        while "INVALID DX FOR SERVICE" in edit_msg:
            sad = edit_msg[:6]
            pos_map = {"SAD 01": (10, 11), "SAD 02": (10, 21), "SAD 03": (10, 31), "SAD 04": (10, 41)}
            if sad in pos_map:
                r_, c_ = pos_map[sad]
                screen.PutString("E", r_, c_); wait_ready(screen)
            send_enter(screen)
            edit_msg = (screen.GetString(31, 2, 78) or "").strip()

    edit_msg = (screen.GetString(31, 2, 78) or "").strip()
    if any(x in edit_msg for x in ("1235-INVALID POS/TOS", "T.O.S.", "SAD")):
        ub_tos_entry(screen, str(row.get("NEW_TOS", "") or "").strip(), str(row.get("OLD_TOS", "") or "").strip(), edit_msg, row)

    if (screen.GetString(1, 5, 3) or "").strip() != "506" and (screen.GetString(1, 74, 3) or "").strip() == "140":
        pass  # would retry — handled by caller

    if settings.get("remv_prcrt_byps", "N") == "Y":
        if "PC# NOT VALID FOR PATIENT" in (screen.GetString(31, 1, 70) or ""):
            screen.MoveTo(2, 12); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString("RP", 2, 5); wait_ready(screen)
            send_enter(screen)

    # Apply State Type
    aply_st_typ = settings.get("aply_st_typ", "N/A")
    edit_msg = (screen.GetString(31, 2, 78) or "").strip()
    if aply_st_typ == "BY SAD ERR" and "318 24 MANUALLY CONTRACTED SVC" in edit_msg:
        sad = edit_msg[:6]
        st_row = {"SAD 01": 18, "SAD 02": 19, "SAD 03": 20, "SAD 04": 21}.get(sad)
        if st_row:
            place_value(screen, str(row.get("STATE_TYPE", "") or "").strip(), st_row, 60)
            send_enter(screen)
    elif aply_st_typ == "ALL LINES":
        for rr in range(18, 22):
            place_value(screen, str(row.get("STATE_TYPE", "") or "").strip(), rr, 60)
        send_enter(screen)

    # Surprise bill UB
    edit_msg = (screen.GetString(31, 2, 78) or "").strip()
    if "SURP BILL" in edit_msg or "SURPRISE BILL" in edit_msg:
        prv = (screen.GetString(22, 6, 1) or "").strip().upper()
        if prv in ("E", "G", "Y"):
            place_value(screen, "}", 22, 6)
            send_enter(screen)

    # Multiple pre-certs
    if "MULTIPLE PRE-CERTS FOUND" in (screen.GetString(31, 2, 78) or ""):
        place_value(screen, str(row.get("PRE_CERT_NO", "") or "").strip(), 2, 12)
        send_enter(screen)

    # CPS506 screen
    if get_screen_id(screen) != "CPS506.01":
        if "SAF" in (screen.GetString(31, 12, 65) or ""):
            screen.PutString("SAF", 5, 31); wait_ready(screen)
            send_enter(screen)
        msg = (screen.GetString(31, 2, 75) or "").strip()
        status_parts.append(f"NOT PROCESSED. {msg}")
        return 0

    # Payee check
    if (screen.GetString(7, 8, 1) or "").strip() == "1" and str(settings.get("payee", "0")) == "0":
        status_parts.append("CHANGE PAYEE TO 1")
        return 0

    # Validate Amt Pd
    if settings.get("vld_amt_pd", "N") == "Y":
        paid, msg = is_fully_paid(screen, "InelCodes", rej_inel, cpt_full_pd)
        if not paid:
            status_parts.append(msg or "NOT PROCESSED. NOT 100% FULLY PD.")
            return 0
    if settings.get("vld_amt_pd_by_cpt", "N") == "Y":
        paid, msg = is_fully_paid(screen, "CPTCodes", rej_inel, cpt_full_pd)
        if not paid:
            status_parts.append(msg or "NOT PROCESSED. NOT 100% FULLY PD.")
            return 0

    if settings.get("amt_858_inq", "N") == "Y":
        existing = str(row.get("AMT_858_TOTAL", "") or "").strip()
        existing_val = float(existing) if existing else 0.0
        row["AMT_858_TOTAL"] = f"{existing_val + float(total_amt_858(screen)):.2f}"
        return 1

    if settings.get("aply_two_ap_cd", "N") == "Y" and str(row.get("AP_CD_2ND", "") or "").strip():
        _ub_ap_code_entry(screen, row)

    if settings.get("updtHic", "N") == "Y":
        if str(row.get("SEQ_NO", "") or "").strip() and str(row.get("NEW_PLAN_ID", "") or "").strip():
            if not str(row.get("HIC_STATUS", "") or "").strip():
                row["HIC_STATUS"] = plan_id_update(screen, row)

    if settings.get("aply_631_inel", "N") == "Y":
        bypass_duplicate(screen, "UB", settings)
    if settings.get("aply_034_inel", "N") == "Y":
        bypass_duplicate(screen, "UB", settings)

    if settings.get("chk_inel", "N") == "Y":
        found, codes_found = check_inel_code(screen, settings.get("ck_inel", {}))
        if found:
            status_parts.append(f"CHECK INEL CODE:{codes_found}")
            return 0

    data_entry_in_cps506(screen, row, settings)
    send_enter(screen)

    if "SAF" in (screen.GetString(31, 12, 65) or ""):
        screen.PutString("SAF", 5, 31); wait_ready(screen)
        send_enter(screen)
    if (screen.GetString(31, 12, 60) or "").strip() == "CRL 37   PROMPT PAY - RLS TYPE R REQUIRED":
        screen.PutString("R", 3, 39); wait_ready(screen)
        send_enter(screen)
    if (screen.GetString(31, 12, 60) or "").strip() == "CRL 36   281136  DENIAL RELEASE CODE REQUIRED":
        screen.PutString("71", 3, 13); wait_ready(screen)
        screen.PutString("Y", 3, 39); wait_ready(screen)
        send_enter(screen)
    if (screen.GetString(31, 12, 60) or "").strip() == "CRL 95   281035DUPLICATE INEL. CODES FOR SAME SERVICE":
        send_pf(screen, 8)
        place_value(screen, "460", 2, 37)
        send_enter(screen)
        for i in range(12, 16):
            if (screen.GetString(i, 14, 3) or "").strip() == "908":
                if not (screen.GetString(i, 2, 11) or "").strip():
                    remove_value(screen, i, 14)
        send_enter(screen)
        if get_screen_id(screen) == "CPS506.01":
            status_parts.append((screen.GetString(31, 2, 60) or "").strip())
            return 0
        data_entry_in_cps506(screen, row, settings)
        send_enter(screen)

    screen_code = (screen.GetString(1, 74, 3) or "").strip()
    if screen_code == "115":
        status_parts.append((screen.GetString(31, 2, 75) or "").strip())
        return 0
    if screen_code == "112":
        status_parts.append("Released.")
        return 1
    else:
        status_parts.append("Not Released. " + (screen.GetString(31, 12, 60) or "").strip().replace("  ", " "))
        if (screen.GetString(1, 74, 3) or "").strip() == "114":
            status_parts.append("Duplicate Claim")
        return 0


# ---------------------------------------------------------------------------
# UB TOS Entry
# ---------------------------------------------------------------------------

def ub_tos_entry(screen, new_tos: str, old_tos: str, edit_msg: str, row: dict):
    sad_line = edit_msg[5:6] if len(edit_msg) > 5 else ""
    tos_primary = {"1": 6, "2": 7, "3": 8, "4": 9}.get(sad_line)
    if tos_primary:
        place_value(screen, new_tos, tos_primary, 14)
        for rr in [6, 7, 8, 9]:
            if rr == tos_primary:
                continue
            v = (screen.GetString(rr, 40, 11) or "").strip()
            if v in (".00", ".01") and v:
                place_value(screen, new_tos, rr, 14)

    for rr in range(12, 16):
        if (screen.GetString(rr, 14, 3) or "").strip() == old_tos:
            place_value(screen, str(row.get("NEW_INEL_CD", "") or "").strip() or old_tos, rr, 14)

    place_value(screen, "x", 29, 71)
    send_enter(screen)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_ub_oi_elig_pd(screen, row, p, setting):
    elig = str(row.get("NEW_OI_ELIG", "") or "").strip()
    pd_val = str(row.get("NEW_OI_PD", "") or "").strip()
    line_map = {"1ST LINE": 18, "2ND LINE": 19, "3RD LINE": 20, "4TH LINE": 21}
    if setting == "N/A":
        return
    if setting == "ALL LINES":
        if elig:
            screen.MoveTo(p + 12, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString(elig, p + 12, 2); wait_ready(screen)
        if pd_val:
            screen.MoveTo(p + 12, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString(pd_val, p + 12, 14); wait_ready(screen)
    elif setting in line_map:
        rr = line_map[setting]
        if elig:
            screen.MoveTo(rr, 2); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString(elig, rr, 2); wait_ready(screen)
        if pd_val:
            screen.MoveTo(rr, 14); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
            screen.PutString(pd_val, rr, 14); wait_ready(screen)


def _apply_new_oi_indicator_ub(screen, row, p, setting):
    ind = str(row.get("NEW_OI_IND", "") or "").strip()
    line_map = {"1ST LINE": 18, "2ND LINE": 19, "3RD LINE": 20, "4TH LINE": 21}
    if setting == "N/A" or not ind:
        return
    if setting == "ALL LINES":
        remove_value(screen, p + 12, 26); place_value(screen, ind, p + 12, 26)
    elif setting in line_map:
        rr = line_map[setting]
        screen.MoveTo(rr, 26); wait_ready(screen); screen.SendKeys("<EraseEOF>"); wait_ready(screen)
        screen.PutString(ind, rr, 26); wait_ready(screen)


def _ub_ap_code_entry(screen, row):
    if (screen.GetString(1, 5, 6) or "").strip() == "506.01":
        send_pf(screen, 8)
        place_value(screen, "460", 2, 37)
        send_enter(screen)
        l = 0
        for i in range(6, 10):
            if (screen.GetString(i, 4, 6) or "").strip():
                place_value(screen, str(row.get("AP_CD_2ND", "") or "").strip(), 10, 54 + l)
            l += 3
    place_value(screen, "x", 29, 71)
    send_enter(screen)
