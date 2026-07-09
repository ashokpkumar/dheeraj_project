

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


def get_extra_system():
    """
    Dispatch a handle to the EXTRA.System COM object, initializing COM for
    the calling thread first (required since sessions are often attached
    from worker threads).
    """
    if win32com is None:
        raise RuntimeError("win32com (pywin32) is not available on this host (Windows required).")

    import pythoncom
    pythoncom.CoInitialize()

    return win32com.client.Dispatch("EXTRA.System")


def iter_live_emulator_sessions(system=None):
    """
    Yield (index, session) for each EXTRA session in System.Sessions that is
    actually alive. System.Sessions can contain stale/zombie entries whose
    underlying process is gone — those raise an IPC error on almost any
    property access, including .Screen, so each candidate is sanity-checked
    and skipped rather than yielded.
    """
    system = system or get_extra_system()
    sessions = system.Sessions
    for i in range(1, sessions.Count + 1):
        try:
            sess = sessions.Item(i)
            sess.Screen  # sanity check the session is actually alive
        except Exception:
            continue
        yield i, sess


def attach_emulator_sessions(n=4):
    """
    Attach to up to `n` live, open EXTRA emulator sessions and return them
    as a list.
    """
    result = []
    for _, sess in iter_live_emulator_sessions():
        result.append(sess)
        if len(result) >= n:
            break

    if not result:
        raise RuntimeError("No live emulator sessions found (all were stale/disconnected).")

    # Optional: give host a moment to be quiet
    for s in result:
        try:
            s.Screen.WaitHostQuiet(2000)
        except Exception:
            pass

    return result


def get_active_screen():
    """
    Return the Screen for the EXTRA.System's ActiveSession. This is the
    single entry point every caller should use to grab "the current"
    emulator screen (as opposed to attaching multiple sessions).
    """
    system = get_extra_system()
    sess = system.ActiveSession
    if sess is None:
        raise RuntimeError("ActiveSession is None — is the emulator open?")
    screen = sess.Screen
    if screen is None:
        raise RuntimeError("Screen object is None — emulator may not be ready")
    return screen

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
