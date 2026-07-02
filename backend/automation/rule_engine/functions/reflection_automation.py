import os
import time
import win32com.client
import pythoncom
from rule_engine.registry import register_function
from .helpers import (
    get_screen_id,
    wait_for_screen,
    send_enter,
    place_value,
)


def _get_open_session_names() -> set:
    """Return the set of currently open EXTRA session names (uppercased), empty if EXTRA is not running."""
    try:
        pythoncom.CoInitialize()
        system = win32com.client.Dispatch("EXTRA.System")
        names = set()
        for i in range(1, system.Sessions.Count + 1):
            try:
                name = (system.Sessions.Item(i).Name or "").strip().upper()
            except Exception:
                continue
            if name:
                names.add(name)
        return names
    except Exception:
        return set()


def _attach_named_screens(expected_names) -> dict:
    """
    Scan every EXTRA session (System.Sessions can accumulate stale/zombie
    entries whose underlying process is gone) and return {name: screen}
    for the ones we can positively identify by name. Zombie entries raise
    an IPC error on almost any property access, including .Screen — those
    are skipped rather than allowed to crash the whole attach.
    """
    pythoncom.CoInitialize()
    system = win32com.client.Dispatch("EXTRA.System")
    total = system.Sessions.Count

    remaining = {n.upper(): n for n in expected_names}
    found = {}

    for i in range(1, total + 1):
        if not remaining:
            break
        try:
            sess = system.Sessions.Item(i)
            name = (sess.Name or "").strip().upper()
        except Exception:
            continue  # zombie/stale session entry — skip

        if name not in remaining:
            continue

        try:
            found[remaining[name]] = sess.Screen
        except Exception:
            continue  # session reports a name but its Screen is dead too
        del remaining[name]

    return found


def _read(screen, row, col, length):
    wait_for_screen(screen)
    return screen.GetString(row, col, length).strip()


def _wait_for_text(screen, row, col, length, keyword, timeout=20):
    for _ in range(timeout):
        if keyword.upper() in _read(screen, row, col, length).upper():
            return True
        time.sleep(1)
    return False


# ---------------------------------------------------------------------------
# Screen detection
# ---------------------------------------------------------------------------

def _detect_screen(screen) -> str:
    """
    Returns one of:
      'done'     — already on any CPS screen, no action needed
      'tpx_menu' — stuck on TPX MENU
      'login'    — stuck on login/Userid screen
      'entry'    — stuck on entry screen (UHC0010)
      'unknown'  — unrecognised screen, fall back to full login flow
    """
    sid = get_screen_id(screen)  # reads (1, 2, 10)
    if sid.upper().startswith("CPS"):
        return "done"
    if "TPX MENU" in _read(screen, 1, 25, 8).upper():
        return "tpx_menu"
    if "USERID" in _read(screen, 16, 5, 6).upper():
        return "login"
    if "UHC0010" in _read(screen, 2, 1, 27).upper():
        return "entry"
    return "unknown"


# ---------------------------------------------------------------------------
# Navigation steps
# ---------------------------------------------------------------------------

def _step_entry_screen(screen):
    """Confirm UHC0010 at (2,1), type UMR at (3,1), press Enter."""
    if not _wait_for_text(screen, 2, 1, 27, "UHC0010"):
        return False, "Entry screen not detected — 'UHC0010' not found at (2,1)"
    place_value(screen, "UMR", 3, 1)
    send_enter(screen)
    return True, "Entry screen OK"


def _step_login_screen(screen):
    """Confirm Userid at (16,5), fill credentials, press Enter, confirm TPX MENU."""
    if not _wait_for_text(screen, 16, 5, 6, "Userid"):
        return False, "Login screen not detected — 'Userid' not found at (16,5)"
    place_value(screen, "RAUWTVW", 16, 20)
    place_value(screen, "DP$#2RAJ", 17, 20)
    send_enter(screen)
    if not _wait_for_text(screen, 1, 25, 8, "TPX MENU"):
        return False, "TPX MENU not confirmed after login"
    return True, "Login screen OK"


def _step_tpx_menu(screen):
    """Confirm TPX MENU at (1,25), Enter at (18,4); if not already on a CPS screen, type GJBB at (1,1) and Enter; confirm CPS515.01."""
    if not _wait_for_text(screen, 1, 25, 8, "TPX MENU"):
        return False, "TPX MENU not detected at (1,25)"
    screen.moveTo(18, 4)
    send_enter(screen)

    if not get_screen_id(screen).upper().startswith("CPS"):
        place_value(screen, "GJBB", 1, 1)
        send_enter(screen)

    if not _wait_for_text(screen, 1, 2, 9, "CPS515.01"):
        return False, "Claim screen not reached — 'CPS515.01' not found at (1,2)"
    return True, "Claim main screen reached"


def _automate_session(screen, name):
    state = _detect_screen(screen)

    if state == "done":
        return {"name": name, "success": True, "message": "Already on claim screen — no action needed."}

    steps = {
        "tpx_menu": [_step_tpx_menu],
        "login":    [_step_login_screen, _step_tpx_menu],
    }.get(state, [_step_entry_screen, _step_login_screen, _step_tpx_menu])  # entry / unknown

    for step_fn in steps:
        ok, msg = step_fn(screen)
        if not ok:
            return {"name": name, "success": False, "message": msg}
    return {"name": name, "success": True, "message": "Reached Claim main screen (CPS515.01)"}


# ---------------------------------------------------------------------------
# Registered function
# ---------------------------------------------------------------------------

@register_function(
    name="open_emulator",
    inputs=[
        {"name": "location", "type": "string"},
    ],
    outputs=[
        {"name": "success", "type": "boolean"},
        {"name": "sessions", "type": "array"},
        {"name": "message", "type": "string"},
    ]
)
def open_emulator(location, context=None):
    if not os.path.isdir(location):
        return {"success": False, "sessions": [], "message": f"Directory not found: {location}"}

    rd3x_files = [f for f in os.listdir(location) if f.endswith(".rd3x")]
    if not rd3x_files:
        return {"success": False, "sessions": [], "message": f"No .rd3x files found in: {location}"}

    # session name (derived from filename) -> rd3x filename
    file_by_name = {os.path.splitext(f)[0]: f for f in rd3x_files}
    session_names = list(file_by_name.keys())

    # Only launch sessions whose name isn't already open — never re-open by position
    open_names = _get_open_session_names()
    missing_names = [name for name in session_names if name.upper() not in open_names]

    if not missing_names:
        msg = f"All {len(session_names)} emulator session(s) are already open — skipping launch."
    else:
        for name in missing_names:
            os.startfile(os.path.join(location, file_by_name[name]))
        msg = (
            f"Opened {len(missing_names)} session(s): {', '.join(missing_names)} "
            f"({len(session_names) - len(missing_names)} were already running)."
        )
        time.sleep(30)

    # Scan every open session (skipping stale/zombie entries) and map by name
    try:
        named_sessions = _attach_named_screens(session_names)
    except Exception as e:
        return {"success": False, "sessions": [], "message": f"Failed to attach to emulator sessions: {e}"}

    results = []
    for name in session_names:
        if name not in named_sessions:
            results.append({"name": name, "success": False, "message": "Session not available"})
            continue
        result = _automate_session(named_sessions[name], name)
        results.append(result)

    all_ok = all(r["success"] for r in results)
    return {
        "success": all_ok,
        "sessions": results,
        "message": f"{msg} Processed {len(results)} session(s). {sum(r['success'] for r in results)} succeeded.",
    }
