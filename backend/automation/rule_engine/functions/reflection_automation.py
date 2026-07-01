import os
import time
import win32com.client
import pythoncom
from rule_engine.registry import register_function
from .helpers import (
    attach_emulator_sessions,
    get_screen_id,
    wait_for_screen,
    send_enter,
    place_value,
)

TARGET_SESSIONS = 4


def _is_visible_session(session) -> bool:
    """Return True only if the EXTRA session has a visible, interactive window."""
    try:
        return bool(session.Visible)
    except Exception:
        return False


def _count_open_sessions() -> int:
    """Return the number of visible (foreground) EXTRA sessions, ignoring background processes."""
    try:
        pythoncom.CoInitialize()
        # GetActiveObject attaches to the running EXTRA instance without taking
        # ownership — releasing this reference will NOT close EXTRA.
        system = win32com.client.GetActiveObject("EXTRA.System")
        return sum(
            1 for i in range(1, system.Sessions.Count + 1)
            if _is_visible_session(system.Sessions.Item(i))
        )
    except Exception:
        return 0


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
      'done'     — already on CPS515.01 or CPS520.01, no action needed
      'tpx_menu' — stuck on TPX MENU
      'login'    — stuck on login/Userid screen
      'entry'    — stuck on entry screen (UHC0010)
      'unknown'  — unrecognised screen, fall back to full login flow
    """
    sid = get_screen_id(screen)  # reads (1, 2, 10)
    if sid in ("CPS515.01", "CPS520.01"):
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
    """Confirm TPX MENU at (1,25), Enter at (18,4), type GJBB at (1,1), Enter, confirm CPS515.01."""
    if not _wait_for_text(screen, 1, 25, 8, "TPX MENU"):
        return False, "TPX MENU not detected at (1,25)"
    screen.moveTo(18, 4)
    send_enter(screen)
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

    # Check how many sessions are already open and only launch what is missing
    already_open = _count_open_sessions()
    needed = max(0, TARGET_SESSIONS - already_open)

    if needed == 0:
        msg = f"All {TARGET_SESSIONS} emulator sessions are already open — skipping launch."
    else:
        files_to_open = rd3x_files[:needed]
        for filename in files_to_open:
            os.startfile(os.path.join(location, filename))
        msg = f"Opened {len(files_to_open)} session(s) ({already_open} were already running)."
        time.sleep(30)

    # Attach to all TARGET_SESSIONS sessions via EXTRA COM (from helpers)
    try:
        emulator_sessions = attach_emulator_sessions(TARGET_SESSIONS)
    except RuntimeError as e:
        return {"success": False, "sessions": [], "message": str(e)}

    # Drop background/hidden sessions — only keep ones with a visible window
    visible_sessions = [s for s in emulator_sessions if _is_visible_session(s)]

    # Pair visible sessions with filenames by open order, build name -> screen map
    session_names = [os.path.splitext(f)[0] for f in rd3x_files[:TARGET_SESSIONS]]
    named_sessions = {
        name: visible_sessions[i].Screen
        for i, name in enumerate(session_names)
        if i < len(visible_sessions)
    }

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
