"""
TOD (Type of Diagnosis) update — port of Modules_oTOD.txt VBA.
"""

from .utils import get_screen_id, place_value, remove_value, send_enter, send_pf


def check_tod(row: dict) -> bool:
    """Mirrors VBA CheckTOD."""
    my_tod = str(row.get("TOD", "") or "").strip()
    if not my_tod:
        return False
    if not my_tod.isdigit():
        return False
    if len(my_tod) > 2:
        return False
    return True


def tod_update(screen, row: dict, settings: dict) -> bool:
    """
    Mirrors VBA TOD_Update.
    Navigates to the condition screen and updates the TOD for all conditions
    with value '99' or '00'.
    Returns True on success, False on failure (sets row['MACRO_STATUS'] on failure).
    """
    if not check_tod(row):
        row["MACRO_STATUS"] = "CHECK TOD VALUE"
        return False

    ccn = str(row.get("CLAIM_NO", "") or "").strip()

    # EntryPoint1: ensure we're on CPS520.01, then enter claim number
    for _ in range(15):
        sid = get_screen_id(screen)
        if sid == "CPS520.01":
            place_value(screen, ccn, 8, 15)
            remove_value(screen, 9, 15)
            remove_value(screen, 12, 15)
            break
        send_pf(screen, 9)
    else:
        send_pf(screen, 9)
        place_value(screen, ccn, 8, 15)
        remove_value(screen, 9, 15)
        remove_value(screen, 12, 15)

    send_enter(screen)

    if get_screen_id(screen) == "CPS520.01":
        # Did not advance — error on message line
        row["MACRO_STATUS"] = (screen.GetString(31, 2, 70) or "").strip()
        return False

    # Navigate to draft 01, then enter condition select
    place_value(screen, "01", 3, 26)
    send_enter(screen)
    place_value(screen, "X", 29, 9)
    send_enter(screen)

    pg_ctr = 0
    while True:
        for k in range(4, 19, 2):
            my_tod = (screen.GetString(k, 34, 2) or "").strip()
            my_rcn = (screen.GetString(k, 5, 3) or "").strip()

            if my_tod in ("99", "00"):
                place_value(screen, my_rcn, 2, 18)
                place_value(screen, "X", 29, 55)
                send_enter(screen)
                tod_val = str(row.get("TOD", "")).strip().zfill(2)
                place_value(screen, tod_val, 5, 60)
                send_enter(screen)
                if get_screen_id(screen) != "CPS910.01":
                    # Go back to condition list
                    send_pf(screen, 8)
                    place_value(screen, "850", 2, 37)
                    send_enter(screen)
                    place_value(screen, "X", 29, 9)
                    send_enter(screen)
                    for _ in range(pg_ctr):
                        send_pf(screen, 11)
                else:
                    row["MACRO_STATUS"] = (screen.GetString(31, 2, 60) or "").strip()
                    return False

            if not my_rcn:
                break

        # Try to advance to the next page of conditions
        send_pf(screen, 11)
        msg31 = (screen.GetString(31, 2, 65) or "").strip()
        if msg31 == "YOU MAY NOT PAGE FORWARD AT THIS TIME":
            break
        pg_ctr += 1

    return True
