"""
Screen primitives and per-claim-type reversal helpers for the Same Day
Reversal macro. Ports Current_Session / PlaceValue / InCorrectScreen and the
HCFA / UB reversal blocks of Draft_Reveral_9994 from
Macros/Same_Day_Reversal/oIShared.txt.
"""


# ---------------------------------------------------------------------------
# Screen primitives (mirror oIShared.txt helpers)
# ---------------------------------------------------------------------------

def wait_ready(screen):
    while screen.OIA.XStatus != 0:
        pass


def get_screen_id(screen) -> str:
    """Screen id field used throughout this macro (row 1, col 71, len 10)."""
    wait_ready(screen)
    return (screen.GetString(1, 71, 10) or "").strip()


def in_correct_screen(screen, scrn_val: str, r: int, c: int, length: int) -> bool:
    """Mirrors InCorrectScreen VBA."""
    wait_ready(screen)
    return (screen.GetString(r, c, length) or "").strip() == scrn_val


def place_value(screen, val, r: int, c: int):
    """Mirrors PlaceValue VBA."""
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


def send_enter(screen):
    screen.SendKeys("<Enter>")
    wait_ready(screen)


def send_pf(screen, n: int):
    screen.SendKeys(f"<PF{n}>")
    wait_ready(screen)


# ---------------------------------------------------------------------------
# Per-claim-type config — HCFA (BLX143.01) vs UB (BLX143) blocks in
# Draft_Reveral_9994 are near-identical, differing only by field positions.
# ---------------------------------------------------------------------------

_CLAIM_TYPE_CONFIG = {
    "HCFA": dict(
        ds_screen_id="BLX143.01",
        ds_row=3, ds_col=28, ds_step=14, ds_limit=17,
        check_f1f11=True, count_page_row=31,
        svc_pos=(1, 22), clrvs_pos=(29, 67),
        status_pos=(31, 2, 70),
    ),
    "UB": dict(
        ds_screen_id="BLX143",
        ds_row=7, ds_col=27, ds_step=12, ds_limit=19,
        check_f1f11=False, count_page_row=32,
        svc_pos=(1, 21), clrvs_pos=(31, 62),
        status_pos=(31, 12, 70),
    ),
}


def _count_service_display(screen, cfg: dict) -> int:
    """
    Counts distinct service-display groups, paging with PF11 as needed.
    Mirrors the dsCount Do-While loop in each Case block. Note: the VBA
    always resets the read cursor to row 3 after paging forward (even in the
    UB block, whose loop starts at row 7) — preserved here as-is rather than
    "fixed", since this is a faithful port of the original macro.
    """
    i = cfg["ds_row"]
    ds_pattern = (screen.GetString(i, cfg["ds_col"], 4) or "").strip()
    ds_count = 1
    while (screen.GetString(i, cfg["ds_col"], 4) or "").strip():
        current = (screen.GetString(i, cfg["ds_col"], 4) or "").strip()
        if ds_pattern != current:
            ds_pattern = current
            ds_count += 1
        if i < cfg["ds_limit"]:
            i += cfg["ds_step"]
        else:
            do_page = True
            if cfg["check_f1f11"]:
                do_page = "F1/F11" in (screen.GetString(29, 74, 4) or "").strip()
            if do_page:
                send_pf(screen, 11)
                if (screen.GetString(cfg["count_page_row"], 2, 60) or "").strip() == \
                        "YOU MAY NOT PAGE FORWARD AT THIS TIME":
                    break
            i = 3
    return ds_count


def _count_lines(screen) -> int:
    """
    Mirrors the HCFAReadLineNumbers / UBReadLineNumbers GoTo loop: pages
    through the draft list with PF11, accumulating rows-with-data (col 2,
    len 2) until a 'YOU MAY NOT PAGE FORWARD AT THIS TIME' message appears
    on row 31 or 32. Identical between the HCFA and UB blocks.
    """
    ln_cntr = 0
    while True:
        r = 9
        while (screen.GetString(r, 2, 2) or "").strip():
            ln_cntr += 1
            r += 2
        send_pf(screen, 11)
        msg31 = (screen.GetString(31, 2, 60) or "").strip()
        msg32 = (screen.GetString(32, 2, 60) or "").strip()
        if msg31 == "YOU MAY NOT PAGE FORWARD AT THIS TIME" or \
                msg32 == "YOU MAY NOT PAGE FORWARD AT THIS TIME":
            break
    return ln_cntr


def _reverse_lines(screen, ccn: str, cfg: dict, ln_cntr: int) -> str:
    """
    Mirrors the shared 'For i = 1 To lnCntr' reversal loop (identical body in
    both the HCFA and UB blocks apart from the per-type positions in `cfg`).
    Returns the final status string; "CLAIM REVERESED" (sic — matches the
    VBA literal) on success.
    """
    r = 9
    ln_no = 1
    for i in range(1, ln_cntr + 1):
        send_pf(screen, 7)
        place_value(screen, ccn, 13, 45)
        place_value(screen, "x", 16, 45)  # Search all family
        send_enter(screen)
        place_value(screen, "1", *cfg["svc_pos"])    # SVC
        place_value(screen, "x", *cfg["clrvs_pos"])  # CLRVS
        send_enter(screen)

        if get_screen_id(screen) == cfg["ds_screen_id"]:
            ds_val = (screen.GetString(cfg["ds_row"], cfg["ds_col"], 4) or "").strip()
            sr, sc, sl = cfg["status_pos"]
            return f"DS: {ds_val} | {(screen.GetString(sr, sc, sl) or '').strip()}"

        if not in_correct_screen(screen, "BLX152.01", 1, 71, 10):
            return "BLX152.01/CPS611.01: UNABLE TO MAPP CHECK REVERSAL SCREEN"

        if in_correct_screen(screen, "CPS701.01", 1, 2, 10):
            return "NOT REVERSED: MEDICAL ADJUSTMENT REQUEST SCREEN"

        if 6 <= i <= 10:
            if i == 6:
                r, ln_no = 9, 1
            send_pf(screen, 11)
        elif 11 <= i <= 15:
            if i == 11:
                r, ln_no = 9, 1
            send_pf(screen, 11)
            send_pf(screen, 11)

        if (screen.GetString(r, 44, 2) or "").strip() != "99":
            place_value(screen, f"{ln_no:02d}", 2, 10)  # "01" default
            place_value(screen, "99", 2, 23)
            place_value(screen, "94", 2, 36)
            send_enter(screen)
            if in_correct_screen(screen, "BLX152.01", 1, 71, 10):
                return (screen.GetString(31, 2, 70) or "").strip()

        r += 2
        ln_no += 1

    return "CLAIM REVERESED"


def run_claim_type_reversal(screen, claim_type: str, ccn: str, rw_result: dict) -> str:
    """
    Mirrors the BLX143.01 (HCFA) / BLX143 (UB) Case blocks of
    Draft_Reveral_9994. Populates rw_result['CLAIM_TYPE'] / ['DS_COUNT'] and
    returns the final status string (mirrors sheet columns C / E / G).
    """
    cfg = _CLAIM_TYPE_CONFIG[claim_type]
    rw_result["CLAIM_TYPE"] = claim_type

    if not (screen.GetString(cfg["ds_row"], cfg["ds_col"], 4) or "").strip():
        return "NO SERVICE DISPLAY DATA"

    rw_result["DS_COUNT"] = _count_service_display(screen, cfg)

    send_pf(screen, 7)
    place_value(screen, ccn, 13, 45)
    place_value(screen, "x", 16, 45)  # Search all family
    send_enter(screen)
    place_value(screen, "1", *cfg["svc_pos"])    # SVC
    place_value(screen, "x", *cfg["clrvs_pos"])  # CLRVS
    send_enter(screen)

    ln_cntr = _count_lines(screen)

    return _reverse_lines(screen, ccn, cfg, ln_cntr)
