

# Windows-only: requires pywin32
try:
    import win32com.client  # pywin32
except Exception:
    win32com = None
from typing import Dict, Optional
import time

from rule_engine.models import ClaimsData

from django.db import transaction



def bulk_upsert_claims(data_list: list[dict],rule_name:str,manual:bool,rule_engine_id :str):
    """
    Upsert behavior with minimal queries:
    - 1 query to fetch existing keys
    - 1 bulk_create for new
    - 1 bulk_update for existing
    """
    

    to_create = []

    for row in data_list:
    
        to_create.append(
            ClaimsData(
                claims_id=row['CLAIM CONTROL #'],
                rule_name=rule_name,
                manual=manual,
                status=row["MACRO STATUS"],
                rule_engine_id =  rule_engine_id

            )
        )

    with transaction.atomic():
        created_count = 0
        ClaimsData.objects.bulk_create(to_create, batch_size=1000)
        
    return {"created": created_count, "updated": 0}


def wait_for_screen(screen, timeout=15):
    start = time.time()
    while screen.OIA.Xstatus != 0:
        if time.time() - start > timeout:
            raise TimeoutError("Emulator screen not ready")
        time.sleep(0.1)

def get_screen_id(screen) -> str:
    try:
        return screen.GetString(1, 2, 10).strip()
    except Exception:
        return ""

def send_enter(screen):
    screen.SendKeys("<ENTER>")
    wait_for_screen(screen)

def send_pf(screen, n: int):
    screen.SendKeys(f"<PF{n}>")
    wait_for_screen(screen)

def send_erase_eof(screen):
    screen.SendKeys("<EraseEOF>")
    wait_for_screen(screen)

def place_value(screen, val: str, r: int, c: int):
    if val is None:
        return
    val = str(val).strip()
    if not val:
        return
    screen.moveTo(r, c)
    send_erase_eof(screen)
    screen.Putstring(val, r, c)

def clean_name(nm: str) -> str:
    parts = [p.strip() for p in (nm or "").split(" ") if p.strip()]
    return " ".join(parts)

def rtn_patient_seq_no(screen, seq_no: str) -> int:
    """
    Attempt to find the row for a patient sequence number on the listing screen.
    Returns the row number if found, else 0.
    """
    seq_no = (seq_no or "").strip()
    if not seq_no:
        return 0

    while True:
        try:
            marker = screen.GetString(9, 2, 70).strip()
        except Exception:
            marker = ""
        for r in range(9, 24, 2):
            try:
                cell = screen.GetString(r, 2, 2).strip()
            except Exception:
                cell = ""
            if cell and cell == seq_no:
                return r
        # Go to next page and check if we've looped
        send_pf(screen, 11)
        try:
            marker2 = screen.GetString(9, 2, 70).strip()
        except Exception:
            marker2 = ""
        if marker == marker2:
            return 0


# =========================
#  Field Capture Routines
# =========================

def read_cps850_fields(screen) -> dict:
    out = {}
    out["EMPLOYEE"] = clean_name(screen.GetString(2, 7, 37).strip())
    out["SSN"] = screen.GetString(3, 72, 9).strip()
    out["CERT"] = screen.GetString(2, 72, 9).strip()
    out["MBR ID"] = screen.GetString(3, 50, 8).strip()
    out["MBR OPI"] = screen.GetString(2, 2, 4).strip()
    out["OPI2"] = screen.GetString(3, 2, 4).strip()
    out["CUSTOMER"] = screen.GetString(6, 50, 26).strip()
    out["PLAN #"] = screen.GetString(7, 50, 12).strip()
    out["EE EFF DT"] = screen.GetString(6, 16, 6).strip()
    out["EE TERM DT"] = screen.GetString(6, 29, 6).strip()
    out["EE CLASS"] = screen.GetString(6, 6, 3).strip()
    out["EE STATUS"] = screen.GetString(6, 13, 2).strip()
    out["DEP EFF DT"] = screen.GetString(7, 16, 6).strip()
    out["DEP TERM DT"] = screen.GetString(7, 29, 6).strip()
    out["DEP CLASS"] = screen.GetString(7, 6, 3).strip()
    out["WORK STATUS"] = screen.GetString(4, 51, 2).strip()
    out["PAID THRU DT"] = screen.GetString(8, 7, 6).strip()
    out["EE REPORTING"] = ""
    out["CSR NOTE"] = screen.GetString(9, 2, 58).strip() + "\n" + screen.GetString(10, 2, 58).strip()
    out["DATE OF BIRTH"] = screen.GetString(2, 55, 6).strip()
    out["EFFECTIVE DATE"] = screen.GetString(13, 40, 6).strip()
    out["REL"] = screen.GetString(13, 60, 2).strip()
    out["TERM DATE"] = screen.GetString(13, 50, 6).strip()
    out["CONTINUING COV"] = screen.GetString(6, 36, 1).strip()
    out["DATE"] = ""
    out["WAITING PERIOD"] = ""
    out["MARITAL STATUS"] = screen.GetString(2, 65, 1).strip()
    out["CLAIM PND IND"] = screen.GetString(13, 79, 2).strip()
    out["PRE-EX MET DT"] = ""
    out["FLEX ROLLOVER"] = ""
    out["PAY EMPLOYEE"] = ""
    out["ALTERNATE ADDRESS"] = ""
    out["PROIVDER NAME"] = screen.GetString(14, 6, 29).strip()
    out["BILLING NAME"] = screen.GetString(1, 39, 31).strip()
    out["TAX ID"] = screen.GetString(14, 40, 9).strip()
    out["OPI"] = screen.GetString(15, 59, 5).strip()
    out["ADDRESS"] = screen.GetString(3, 7, 38).strip() + "\n" + screen.GetString(4, 7, 38).strip()
    out["CITY"] = screen.GetString(5, 6, 20).strip()
    out["STATE"] = screen.GetString(5, 27, 2).strip()
    out["ZIP"] = screen.GetString(5, 30, 12).strip()
    out["EE DOB"] = screen.GetString(2, 55, 6).strip()
    out["LOCATION"] = screen.GetString(5, 50, 4).strip()
    out["EE TERM STAT"] = screen.GetString(6, 26, 2).strip()
    out["MBR ORG EFF DT"] = screen.GetString(6, 45, 4).strip()
    out["CONTINUING COVERAGE"] = screen.GetString(6, 36, 1).strip()
    out["DEP STATUS"] = screen.GetString(7, 13, 2).strip()
    out["POLICY EFF DT"] = screen.GetString(8, 53, 6).strip()
    out["DEP TERM STATUS"] = screen.GetString(7, 26, 2).strip()
    out[" TERM DATE"] = screen.GetString(8, 64, 7).strip()
    out["DEV COV STATUS"] = screen.GetString(7, 42, 7).strip()
    out["MENTAL VENDOR"] = screen.GetString(8, 77, 4).strip()
    out["FLEX"] = ""
    out["PRE-EX MOS"] = screen.GetString(7, 79, 2).strip()
    out["PRE-CERT"] = screen.GetString(4, 78, 3).strip()
    out["ROLLOVER"] = ""
    out["PRE-EXISTING"] = screen.GetString(6, 80, 1).strip()
    out["FAMILY COVERAGE"] = screen.GetString(12, 2, 3).strip()
    out["UPDATED"] = screen.GetString(12, 6, 6).strip()
    out["OTH INS TYPE"] = screen.GetString(11, 27, 2).strip()
    out["LAST UPDATE DATE"] = screen.GetString(11, 20, 6).strip()
    out["OTH INS EFF DT"] = screen.GetString(11, 30, 6).strip()
    out["OTH INS TERM DT"] = screen.GetString(11, 37, 6).strip()
    out["PROVIDER"] = screen.GetString(14, 6, 29).strip()
    out["BILLING NM"] = screen.GetString(1, 39, 31).strip()
    out[" ADDRESS"] = screen.GetString(15, 2, 25).strip()
    out[" CITY"] = screen.GetString(15, 28, 12).strip()
    out[" STATE"] = screen.GetString(15, 41, 2).strip()
    out[" ZIP"] = screen.GetString(15, 44, 10).strip()
    out["PHONE"] = screen.GetString(14, 59, 13).strip()
    out[" TAX ID"] = screen.GetString(14, 40, 9).strip()
    out["PCP"] = screen.GetString(20, 69, 12).strip()
    out[" OPI"] = screen.GetString(15, 59, 5).strip()
    out["SPECIALTY"] = screen.GetString(19, 70, 3).strip()
    out["TIER"] = screen.GetString(19, 79, 2).strip()
    out["RATE"] = screen.GetString(17, 70, 11).strip()
    out["FINANCIAL INVESTIGATION"] = screen.GetString(18, 70, 11).strip()
    out["TAXONOMY"] = ""
    out["PROVIDER NOTE"] = (
        screen.GetString(16, 2, 62).strip() + "\n" +
        screen.GetString(17, 2, 62).strip() + "\n" +
        screen.GetString(18, 2, 62).strip() + "\n" +
        screen.GetString(19, 2, 62).strip()
    )
    return out

def read_blx2460_fields(screen) -> dict:
    return {
        "UB/HCFA AFV FIELD": screen.GetString(23, 13, 1).strip(),
        "UB/HCFA CONDITION NOTE": screen.GetString(22, 44, 36).strip(),
        "UB TOB": screen.GetString(2, 54, 3).strip(),
    }

def read_cps450_fields(screen) -> dict:
    return {
        "UB/HCFA AFV FIELD": screen.GetString(3, 15, 1).strip(),
        "UB/HCFA CONDITION NOTE": screen.GetString(3, 46, 35).strip(),
        "UB TOB": screen.GetString(2, 54, 3).strip(),
        "HCFA AP CODE": screen.GetString(5, 68, 2).strip(),
        "HCFA CFV FIELD": screen.GetString(3, 17, 1).strip(),
    }

def read_cps310_fields(screen) -> dict:
    return {
        "PROVIDER ": screen.GetString(3, 2, 28).strip(),
        "ADDRESS ": screen.GetString(4, 2, 28).strip(),
        "CITY ": screen.GetString(6, 2, 23).strip(),
        "STATE ": screen.GetString(6, 26, 3).strip(),
        "ZIP ": screen.GetString(6, 30, 11).strip(),
    }

def process_claim(
    screen,
    claim_id: str,
    method: str,
    cert_date_mmddyy: str,
    seq_no: str,
    dental_flag: bool
) -> dict:
    """
    Reproduces the GET_INFORMATION flow for a single claim.
    Returns a dict with business-named fields and a MACRO STATUS.
    """
    result = {
        "CLAIM CONTROL #": claim_id,
        "BG SV DT": "",
        "PATIENT SEQ NO ##": "",
        "MACRO STATUS": ""
    }

    try:
        # PF9 entry
        send_pf(screen, 9)
        max_steps = 500
        steps = 0

        while steps < max_steps:
            steps += 1
            wait_for_screen(screen)
            sid = get_screen_id(screen).upper()

            if sid == "CPS520.01":
                # Claim entry
                if method.upper() == "SEARCH BY CCN":
                    place_value(screen, claim_id, 8, 15)
                elif method.upper() == "SEARCH BY CERT":
                    place_value(screen, claim_id, 9, 15)
                if cert_date_mmddyy:
                    place_value(screen, cert_date_mmddyy, 12, 15)
                if dental_flag:
                    place_value(screen, "D", 9, 59)
                send_enter(screen)

                # If still on CPS520.01, capture status and stop
                if get_screen_id(screen).upper() == "CPS520.01":
                    result["MACRO STATUS"] = (
                        screen.GetString(31, 2, 70).strip() + " " +
                        screen.GetString(30, 2, 70).strip()
                    )
                    break

            elif sid == "CPS215.01":
                send_enter(screen)

            elif sid == "CPS125.01":
                result["MACRO STATUS"] = "MEMBER RECORD NOT FOUND"
                break

            elif sid == "CPS220.01":
                ln_row = rtn_patient_seq_no(screen, (seq_no or "00"))
                if ln_row != 0:
                    screen.Putstring((seq_no or "00"), 2, 6)
                    send_enter(screen)
                else:
                    result["MACRO STATUS"] = "UNABLE TO IDENTIFY SEQ NO"
                    break

            elif sid == "CPS325.01":
                send_pf(screen, 8)
                place_value(screen, "850", 2, 37)
                send_enter(screen)

            elif sid == "CPS500.01":
                send_enter(screen)

            elif sid == "CPS850.01":
                result.update(read_cps850_fields(screen))
                if method.upper() == "SEARCH BY CERT":
                    break
                if dental_flag:
                    break
                send_enter(screen)

            elif sid == "CPS228.01":
                send_enter(screen)

            elif sid == "CPS920.01":
                send_enter(screen)

            elif sid == "BLX2460.01":
                result.update(read_blx2460_fields(screen))
                send_pf(screen, 8)

            elif sid == "CPS450.01":
                result.update(read_cps450_fields(screen))
                send_pf(screen, 8)

            elif sid == "CPS511.01":
                place_value(screen, "310", 2, 37)
                send_enter(screen)

            elif sid == "CPS310.01":
                result.update(read_cps310_fields(screen))
                break

            else:
                result["MACRO STATUS"] = "UNEXPECTED SCREEN MAPPING ERROR."
                break

        # PF9 end-of-claim and mark status done
        send_pf(screen, 9)
        result["MACRO STATUS"] = f"DONE.{result.get('MACRO STATUS', '')}"
        return result

    except Exception as e:
        print(e)
        # Return whatever we captured so far; MACRO STATUS may be empty if an early exception occurred
        return result

def attach_emulator_sessions(n=4):
    """
    Attach to up to `n` already-open EXTRA emulator sessions and return them as a list.
    """
    if win32com is None:
        raise RuntimeError("win32com (pywin32) is not available on this host (Windows required).")

    # Initialize COM for THIS thread (the caller's thread)
    import pythoncom
    pythoncom.CoInitialize()

    # GetActiveObject attaches to the running EXTRA instance without taking
    # ownership — releasing this reference will NOT close EXTRA.
    system = win32com.client.GetActiveObject("EXTRA.System")
    sessions = system.Sessions
    if sessions.Count < 1:
        raise RuntimeError("No active emulator sessions found.")

    # 1-based collection
    result = [sessions.Item(i) for i in range(1, min(n, sessions.Count) + 1)]

    # Optional: give host a moment to be quiet
    for s in result:
        try:
            s.Screen.WaitHostQuiet(2000)
        except Exception:
            pass

    return result

class Helpers():
    
    def place_value(screen, text: str, r: int, c: int) -> None:
        if text is None: return
        s = str(text).strip()
        if not s: return
        _move_to(screen, r, c)
        screen.SendKeys("<EraseEof>"); _wait_ready(screen)
        screen.PutString(s, r, c); _wait_ready(screen)

    def remove_value(screen, r: int, c: int) -> None:
        _move_to(screen, r, c)
        screen.SendKeys("<EraseEof>"); _wait_ready(screen)

    def get_string(screen, r: int, c: int, length: int) -> str:
        _wait_ready(screen)
        return str(screen.GetString(r, c, length)).strip()

    def send_enter(screen) -> None:
        screen.SendKeys("<Enter>"); _wait_ready(screen)

    def send_pf8(screen) -> None:
        screen.SendKeys("<PF8>"); _wait_ready(screen)

    def send_pf9(screen) -> None:
        screen.SendKeys("<PF9>"); _wait_ready(screen)

    def send_pf11(screen) -> None:
        screen.SendKeys("<PF11>"); _wait_ready(screen)
        
    def _wait_ready(screen) -> None:
        while screen.OIA.Xstatus != 0:
            time.sleep(HOST_SETTLE_TIME_MS / 1000.0)

    def _move_to(screen, r: int, c: int) -> None:
        _wait_ready(screen)
        screen.MoveTo(r, c)
        _wait_ready(screen)

    
    def _clear_common_edit_errors(screen) -> None:
        """Resolve common 'EDIT ERROR' prompts (MPIN fields, etc.)."""
        edit = get_string(screen, 30, 1, 20).upper()
        if "EDIT ERROR" in edit:
            # Clear MPIN occurrences
            if get_string(screen, 24, 2, 4) == "MPIN":
                remove_value(screen, 24, 7)
            if get_string(screen, 22, 29, 4) == "MPIN":
                remove_value(screen, 22, 34)
            # Field attribute 201 cleanup (if exposed)
            if get_field_attribute(screen, 4, 35) == "201":
                remove_value(screen, 4, 35)
            if get_field_attribute(screen, 4, 63) == "201":
                remove_value(screen, 4, 63)
            send_enter(screen)

    
        # NEW_OI_ELIG_PD/INDCTR updates
    def _set_elig_pd(row: int):
        if claim.get(NEW_OI_ELIG): remove_value(screen, row, 2);  place_value(screen, claim[NEW_OI_ELIG], row, 2)
        if claim.get(NEW_OI_PD):   remove_value(screen, row, 14); place_value(screen, claim[NEW_OI_PD],   row, 14)

    def _set_oi_ind(row: int):
        if claim.get(NEW_OI_IND): remove_value(screen, row, 26); place_value(screen, claim[NEW_OI_IND], row, 26)

    

    def _wait_ready(screen) -> None:
        """Wait until OIA.Xstatus == 0 (host ready)."""
        while screen.OIA.Xstatus != 0:
            time.sleep(HOST_SETTLE_TIME_MS / 1000.0)

    def _move_to(screen, r: int, c: int) -> None:
        _wait_ready(screen)
        screen.MoveTo(r, c)
        _wait_ready(screen)
    
    def _handle_release_prompts(screen, claim: Dict) -> Optional[bool]:
        """
        Handle CPS506 release prompts and statuses.
        Returns:
        True  => Released
        False => Not released (claim[STAT_EDIT] set)
        None  => Keep processing (e.g., duplicate ineligibility path)
        """
        # SAF prompt
        if "SAF" in get_string(screen, 31, 12, 65):
            place_value(screen, "SAF", 5, 31); send_enter(screen)

        # CRL required prompts
        line = get_string(screen, 31, 12, 60)
        if line == "CRL 37 PROMPT PAY - RLS TYPE R REQUIRED":
            place_value(screen, "R", 3, 39); send_enter(screen)
        if line == "CRL 36 281136 DENIAL RELEASE CODE REQUIRED":
            place_value(screen, "71", 3, 13); place_value(screen, "Y", 3, 39); send_enter(screen)

        # Duplicate ineligibility codes (CRL 95)
        if line == "CRL 95 281035DUPLICATE INEL. CODES FOR SAME SERVICE":
            send_pf8(screen); place_value(screen, "460", 2, 37); send_enter(screen)
            # Remove 908 code if amount1 is blank on rows 12..15
            for i in (12, 13, 14, 15):
                if get_string(screen, i, 14, 3) == "908" and not get_string(screen, i, 2, 11):
                    remove_value(screen, i, 14)
            send_enter(screen)
            # If jumped back to CPS506 due to edits, surface status and stop
            if get_string(screen, 1, 2, 11) == "CPS506.01":
                claim[STAT_EDIT] = get_string(screen, 31, 2, 60)
                return False
            # Otherwise continue UB data entry path
            return None

        # Status codes
        code = get_string(screen, 1, 74, 3)
        if code == "115":
            claim[STAT_EDIT] = get_string(screen, 31, 2, 75)
            return False
        if code == "112":
            claim[STAT_EDIT] = (claim.get(STAT_EDIT, "") + " Released.").strip()
            return True
        # Not released, capture reason; add "Duplicate Claim" if 114
        msg = get_string(screen, 31, 12, 60)
        out = (claim.get(STAT_EDIT, "") + " Not Released. " + msg).strip()
        if code == "114":
            out = (out + " Duplicate Claim").strip()
        claim[STAT_EDIT] = out
        return False
