import pandas as pd

from rule_engine.registry import register_function



@register_function(
    name="oi_yes_run_batch", 
    inputs=[{"name": "search_by", "type": "str"},
            {"name": "action", "type": "str"},
            {"name": "oi_status", "type": "str"},
            {"name": "bg_sv_dt", "type": "str"},
            {"name": "level_mode", "type": "str"},
            {"name": "default_tp", "type": "str"},
            {"name": "TYPE", "type": "str"},
            ], # 
    outputs=[{"name": "success", "type": "bool"},
             {"name": "result", "type": "list"}
             ]
)
def oi_yes_run_batch(
    # df,
 
    search_by: str,          # "CERT" or "CLAIM"
    action: str,             # "UPDATE_OI" or "UPDATE_PLAN_ID"
    oi_status: str,          # "YES" or "NO"
    bg_sv_dt,                # datetime/date or "MM/DD/YYYY"
    session_name: str = None,
    level_mode: str = "FAMILY",   # affects fallback logic (like VBA)
    default_tp: str = "UK",       # default type for other members excluding "00"
    update_date=None,             # if None, uses today's date
    TYPE:str = None,
    context=None
):
    """
    Port of core behavior from the VBA in OI_YES_NO_Macro_VBA_Code.txt:
    - Connects to Reflection (EXTRA.System)
    - For each df row, navigates to CPS520.01 and updates OI or Plan ID fields
    Expected df columns (names can be adapted in your calling code):
      cert_id, seq, plan_id, tp, effect_date, term_date, line_update_date, claim_no
    Returns: list[str] status messages aligned to df order.
    """
    import datetime as _dt

    # --- lazy imports so your module doesn't explode on non-Windows hosts ---
    import win32com.client  # pip install pywin32
    df = context.get("df")
    def _to_mmddyy(v):
        if v is None or v == "":
            return ""
        if isinstance(v, str):
            # accepts "MM/DD/YYYY" or "YYYY-MM-DD"
            try:
                if "/" in v:
                    m, d, y = v.split("/")
                    return f"{int(m):02d}{int(d):02d}{int(y)%100:02d}"
                if "-" in v:
                    y, m, d = v.split("-")
                    return f"{int(m):02d}{int(d):02d}{int(y)%100:02d}"
            except Exception:
                pass
            return v  # already formatted
        if isinstance(v, (_dt.date, _dt.datetime)):
            return v.strftime("%m%d%y")
        return str(v)

    def _wait_ready(screen):
        # equivalent to VBA: Do While .OIA.Xstatus <> 0: DoEvents: Loop
        while screen.OIA.XStatus != 0:
            pass

    def _get_screen_id(screen):
        # VBA checks: Trim(.GetString(1,2,11))
        return (screen.GetString(1, 2, 11) or "").strip()

    def _place(screen, val, r, c):
        val = ("" if val is None else str(val)).strip()
        if not val:
            return
        screen.MoveTo(r, c); _wait_ready(screen)
        screen.SendKeys("<EraseEOF>"); _wait_ready(screen)
        screen.PutString(val, r, c); _wait_ready(screen)

    def _remove(screen, r, c):
        screen.MoveTo(r, c); _wait_ready(screen)
        screen.SendKeys("<EraseEOF>"); _wait_ready(screen)

    def _pf9_to_cps520(screen, max_tries=15):
        # mirror VBA Retry loops that PF9 until CPS520.01
        for _ in range(max_tries):
            if _get_screen_id(screen) == "CPS520.01":
                return True
            screen.SendKeys("<PF9>"); _wait_ready(screen)
        return _get_screen_id(screen) == "CPS520.01"

    # --- session attach (VBA: Current_Session()) ---
    system = win32com.client.Dispatch("EXTRA.System")
    sessions = system.Sessions
    sess =  system.ActiveSession
    screen = sess.Screen

    oi_status = (oi_status or "").strip().upper()
    if oi_status not in {"YES", "NO"}:
        raise ValueError("oi_status must be YES or NO")

    search_by = (search_by or "").strip().upper()
    action = (action or "").strip().upper()

    today = _dt.date.today()
    header_updt = _to_mmddyy(update_date or today)
    bg_mmddyy = _to_mmddyy(bg_sv_dt)

    statuses = []

    for idx, row in df.iterrows():
        print(idx)
        print(row)
        OTH_INS_EFF_DT = row.get("OTH_INS_EFF_DT")
        if OTH_INS_EFF_DT!=pd.NaT:
            try:
                eff = _to_mmddyy(OTH_INS_EFF_DT)
            except:
                eff = None

        OTH_INS_TERMN_DT = row.get("OTH_INS_TERMN_DT")
        if OTH_INS_TERMN_DT!=pd.NaT:
            try:
                term = _to_mmddyy(OTH_INS_TERMN_DT)
            except:
                term = None

        OTH_INS_EFF_DT = row.get("OTH_INS_EFF_DT")
        if OTH_INS_EFF_DT!=pd.NaT:
            try:
                line_updt = _to_mmddyy(today)
            except:
                line_updt = None


        # pull row fields (adapt names as needed)
        cert_id = str(row.get("ENRL_CERT_NBR", "") or "").strip()
        claim_no = str(row.get("claim_no", "") or "").strip()
        seq = row.get("INDIV_SEQ_NBR", "")
        plan_id = str(row.get("OTH_INS_PLAN_ID", "") or "").strip()
        if plan_id == 'nan':
            plan_id = None
        if not TYPE:
            tp = str(row.get("OTH_INS_CD", "") or "").strip()
            if tp=='nan':
                tp = None
        else:
            tp=TYPE
            
       
        if search_by=="CLAIM":
            uniq_id = "CLAIM_"+claim_no+"_"+str(seq)
        elif search_by=="CERT":
            uniq_id = "CERT_"+cert_id+"_"+str(seq)
        else:
            uniq_id = "UNKNW"
        status_msg = "UNKNOWN"

        try:
            if not _pf9_to_cps520(screen):
                statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"UNABLE TO MAP CPS520.01"})
                continue

            # --- enter search keys on CPS520.01 ---
            if search_by == "CERT":
                _place(screen, cert_id, 9, 15)
                _place(screen, bg_mmddyy, 12, 15)
                screen.SendKeys("<Enter>"); _wait_ready(screen)

                sid = _get_screen_id(screen)
                if sid == "CPS125.01":
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"MEMBER NOT FOUND"})
                  
                    screen.SendKeys("<PF9>"); _wait_ready(screen)
                    continue
                if sid == "CPS520.01":
                    # macro reads a message line; we return a generic message
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"SEARCH DID NOT ADVANCE (CHECK INPUT)"})
                    # statuses.append("SEARCH DID NOT ADVANCE (CHECK INPUT)")
                    continue
                if sid != "CPS215.01":
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"UNABLE TO MAP ELIG DISPLAY SCREEN"})
                    
                    # statuses.append("UNABLE TO MAP ELIG DISPLAY SCREEN")
                    screen.SendKeys("<PF9>"); _wait_ready(screen)
                    continue

                # enter to CPS220.01
                screen.SendKeys("<Enter>"); _wait_ready(screen)
                if _get_screen_id(screen) != "CPS220.01":
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"UNABLE TO GET MEMBER INFO"})
                    # statuses.append("UNABLE TO GET MEMBER INFO")
                    screen.SendKeys("<PF9>"); _wait_ready(screen)
                    continue

                # default member 00 and go to OI display (CPS228.01)
                _place(screen, "00", 2, 6)
                _place(screen, "x", 29, 38)
                screen.SendKeys("<Enter>"); _wait_ready(screen)
                if _get_screen_id(screen) != "CPS228.01":
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"UNABLE TO MAP MEMBER OI DISPLAY"})
                    # statuses.append("UNABLE TO MAP MEMBER OI DISPLAY")
                    screen.SendKeys("<PF9>"); _wait_ready(screen)
                    continue

                # go into table CPS226.01
                _place(screen, "x", 29, 17)
                screen.SendKeys("<Enter>"); _wait_ready(screen)

            elif search_by == "CLAIM":
                _place(screen, claim_no, 8, 15)
                screen.SendKeys("<Enter>"); _wait_ready(screen)

                sid = _get_screen_id(screen)
                if sid == "CPS125.01":
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"MEMBER NOT FOUND"})
                    # statuses.append("MEMBER NOT FOUND")
                    screen.SendKeys("<PF9>"); _wait_ready(screen)
                    continue

                # VBA handles CPS500.01 path with extra enters/x selections.
                if sid != "CPS520.01":
                    screen.SendKeys("<Enter>"); _wait_ready(screen)
                    _place(screen, "x", 29, 48)
                    screen.SendKeys("<Enter>"); _wait_ready(screen)

                _place(screen, "x", 29, 17)
                screen.SendKeys("<Enter>"); _wait_ready(screen)

            else:
                raise ValueError("search_by must be CERT or CLAIM")

            # At this point we should be on CPS226.01 table.
            # --- perform action ---
            if action == "UPDATE_PLAN_ID":
                updated = False
                for sc_r in range(4, 25, 5):
                    mbr = (screen.GetString(sc_r, 2, 2) or "").strip()
                    if not mbr:
                        break
                    if str(mbr) == f"{int(seq):02d}":
                        # find a subline (y=0..3) where coverage code is MA/MP/MS/MB
                        for y in range(0, 4):
                            updt_cell = (screen.GetString(sc_r + y, 30, 6) or "").strip()
                            cov = (screen.GetString(sc_r + y, 37, 2) or "").strip()
                            if updt_cell and cov in {"MA", "MP", "MS", "MB"}:
                                _place(screen, line_updt, sc_r + y, 30)
                                _place(screen, plan_id, sc_r + y, 54)
                                screen.SendKeys("<Enter>"); _wait_ready(screen)
                                updated = True
                                break
                        break
                status_msg = "PLAN ID FIELD UPDATED." if updated else "NO CHANGE APPLIED."
                statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":status_msg})
                # statuses.append(status_msg)
                screen.SendKeys("<PF9>"); _wait_ready(screen)
                continue

            if action == "UPDATE_OI":
                # header fields
                _place(screen, oi_status, 2, 18)
                _place(screen, header_updt, 2, 29)

                matched_any = True
                updated_target = False

                while True:
                    # scan visible blocks
                    for sc_r in range(4, 25, 5):
                        mbr = (screen.GetString(sc_r, 2, 2) or "").strip()
                        if not mbr:
                            break

                        if oi_status == "YES":
                            if str(mbr) == f"{int(seq):02d}":
                                _place(screen, line_updt, sc_r, 30)
                                _place(screen, tp, sc_r, 37)
                                _place(screen, eff, sc_r, 40)
                                _place(screen, term, sc_r, 47)
                                _place(screen, plan_id, sc_r, 54)
                                updated_target = True
                            else:
                                # fallback logic inspired by VBA:
                                # - apply default_tp to other members excluding "00"
                                if mbr != "00":
                                    if level_mode.upper() != "FAMILY":
                                        _place(screen, default_tp, sc_r, 37)
                                    else:
                                        # in FAMILY mode: don't overwrite "OP"
                                        current_tp = (screen.GetString(sc_r, 37, 2) or "").strip()
                                        if current_tp != "OP":
                                            _place(screen, default_tp, sc_r, 37)
                                else:
                                    # member "00" may remain untouched unless blank/UK
                                    current_tp = (screen.GetString(sc_r, 37, 2) or "").strip()
                                    if current_tp in {"", "UK"}:
                                        _place(screen, "NO", sc_r, 37)

                        else:  # oi_status == "NO"
                            # clear up to 4 sublines if populated
                            for t in range(0, 4):
                                if (screen.GetString(sc_r + t, 30, 6) or "").strip():
                                    _remove(screen, sc_r + t, 30)
                                    _remove(screen, sc_r + t, 37)
                                    _remove(screen, sc_r + t, 40)
                                    _remove(screen, sc_r + t, 47)
                                    _remove(screen, sc_r + t, 54)
                                else:
                                    break
                            updated_target = True

                    # handle paging like VBA (PF11 when MORE DATA appears)
                    footer = (screen.GetString(29, 2, 79) or "").strip().upper()
                    if "MORE DATA: PF11 PAGE FORWARD" in footer:
                        screen.SendKeys("<PF11>"); _wait_ready(screen)
                        msg31 = (screen.GetString(31, 2, 79) or "").strip().upper()
                        if "YOU MAY NOT PAGE FORWARD" in msg31:
                            break
                        if "INVALID KEY" in msg31:
                            matched_any = False
                            break
                        continue

                    # reached end
                    if not updated_target:
                        matched_any = False
                    break

                if not matched_any:
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"NEEDS FURTHER REVIEW"})
                    #statuses.append("NEEDS FURTHER REVIEW")
                    screen.SendKeys("<PF9>"); _wait_ready(screen)
                    continue

                # save (Enter) and read messages (like VBA checks lines 30/31)
                screen.SendKeys("<Enter>"); _wait_ready(screen)
                msg30 = (screen.GetString(30, 2, 79) or "").strip()
                msg31 = (screen.GetString(31, 2, 79) or "").strip()
                if ("INVALID KEY" in msg31.upper()) or ("ERROR IN HIGHLIGHTED" in msg30.upper()):
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"NEEDS FURTHER REVIEW"})
                    #statuses.append("NEEDS FURTHER REVIEW")
                elif msg30:
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":msg30})
                    #statuses.append(msg30)
                elif msg31:
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":msg31})
                    #statuses.append(msg31)
                else:
                    statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"OI FIELD UPDATED"})
                    #statuses.append("OI FIELD UPDATED")

                screen.SendKeys("<PF9>"); _wait_ready(screen)
                continue

            statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":"UNKNOWN ACTION"})
            #statuses.append("UNKNOWN ACTION")
            screen.SendKeys("<PF9>"); _wait_ready(screen)

        except Exception as e:
            statuses.append({'CLAIM CONTROL #':uniq_id,"MACRO STATUS":f"EXCEPTION: {type(e).__name__}: {e}"})
            #statuses.append(f"EXCEPTION: {type(e).__name__}: {e}")

    return {"success":True,
            "result":statuses
            }

# df = pd.read_excel(r"C:\Users\dpaladi2\Desktop\book_8.xlsx")
# action = "UPDATE_OI"
# oi_status = "YES"
# update_date = "4/13/2026"
# default_tp = "UK"
# bg_sv_dt = "1/1/2026"
# level_mode = "FAMILY"
# search_by = "CERT"
# session_name = ""

# res = run_oi_yes_no_batch(
#     df,
#     search_by,
#     action,             # "UPDATE_OI" or "UPDATE_PLAN_ID"
#     oi_status,          # "YES" or "NO"
#     bg_sv_dt,                # datetime/date or "MM/DD/YYYY"
#     session_name,
#     level_mode,   # affects fallback logic (like VBA)
#     default_tp,       # default type for other members excluding "00"
#     update_date           # if None, uses today's date
# )
