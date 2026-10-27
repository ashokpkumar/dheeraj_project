

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

    Optional "DETAILS" key on a row (dict) is stored as-is in
    ClaimsData.details (JSONField) — lets a caller capture everything it
    extracted for a claim, not just status/decision. Callers that don't pass
    it get the field's default ({}), same as before this was added.
    """


    to_create = []

    for row in data_list:

        to_create.append(
            ClaimsData(
                claims_id=row['CLAIM CONTROL #'],
                rule_name=rule_name,
                manual=manual,
                status=row["MACRO STATUS"],
                rule_engine_id =  rule_engine_id,
                decision=row.get("DECISION", ""),
                details=row.get("DETAILS") or {},

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

def attach_emulator_sessions(n=4):
    """
    Attach to up to `n` live, open EXTRA emulator sessions and return them
    as a list. System.Sessions can contain stale/zombie entries whose
    underlying process is gone — those raise an IPC error on almost any
    property access, including .Screen, so each candidate is sanity-checked
    and skipped rather than returned.
    """
    if win32com is None:
        raise RuntimeError("win32com (pywin32) is not available on this host (Windows required).")

    # Initialize COM for THIS thread (the caller's thread)
    import pythoncom
    pythoncom.CoInitialize()

    system = win32com.client.Dispatch("EXTRA.System")
    sessions = system.Sessions
    if sessions.Count < 1:
        raise RuntimeError("No active emulator sessions found.")

    result = []
    for i in range(1, sessions.Count + 1):
        if len(result) >= n:
            break
        try:
            sess = sessions.Item(i)
            sess.Screen  # sanity check the session is actually alive
        except Exception:
            continue  # zombie/stale session entry — skip
        result.append(sess)

    if not result:
        raise RuntimeError("No live emulator sessions found (all were stale/disconnected).")

    # Optional: give host a moment to be quiet
    for s in result:
        try:
            s.Screen.WaitHostQuiet(2000)
        except Exception:
            pass

    return result
