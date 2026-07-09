import os
import time
from rule_engine.registry import register_function
from .helpers import (
    get_extra_system,
    get_screen_id,
    iter_live_emulator_sessions,
    wait_for_screen,
    send_enter,
    place_value,
)


def _close_window(hwnd, timeout=3) -> None:
    """Post WM_CLOSE to a window and, if a 'Cannot save' style dialog pops
    up as a result, dismiss it with 'No' so the window doesn't get stuck."""
    try:
        import win32gui
        import win32con
    except ImportError:
        return

    try:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        return

    deadline = time.time() + timeout
    while time.time() < deadline:
        if not win32gui.IsWindow(hwnd):
            return

        dialogs = []

        def _enum_top(candidate, _):
            if win32gui.IsWindowVisible(candidate) and win32gui.GetClassName(candidate) == "#32770":
                dialogs.append(candidate)
            return True

        win32gui.EnumWindows(_enum_top, None)

        for dlg in dialogs:
            no_buttons = []

            def _enum_child(child, _):
                if (
                    win32gui.GetClassName(child) == "Button"
                    and win32gui.GetWindowText(child).strip().upper() == "NO"
                ):
                    no_buttons.append(child)
                return True

            win32gui.EnumChildWindows(dlg, _enum_child, None)
            if no_buttons:
                win32gui.SendMessage(no_buttons[0], win32con.BM_CLICK, 0, 0)

        time.sleep(0.25)


def _close_all_sessions():
    """
    Close every currently open EXTRA session AND its window so we always
    start from a clean slate — Session.Close() only ends the session; the
    window it was hosted in stays open and has to be closed separately via
    its WindowHandle. Closing shifts the collection's indices, so walk it
    back-to-front. Any session that errors along the way (already dead) is
    just skipped.
    """
    system = get_extra_system()
    for i in range(system.Sessions.Count, 0, -1):
        try:
            sess = system.Sessions.Item(i)
        except Exception:
            continue

        try:
            hwnd = sess.WindowHandle
        except Exception:
            hwnd = None

        try:
            sess.Close()
        except Exception:
            pass

        if hwnd:
            _close_window(hwnd)


def _attach_named_sessions(expected_names) -> dict:
    """
    Scan open EXTRA sessions and return {name: session} for the ones we can
    positively identify by name. Any session that errors on property access
    is skipped rather than allowed to crash the whole attach.
    """
    remaining = {n.upper(): n for n in expected_names}
    found = {}

    for _, sess in iter_live_emulator_sessions():
        if not remaining:
            break
        try:
            name = (sess.Name or "").strip().upper()
        except Exception:
            continue

        if name not in remaining:
            continue

        found[remaining[name]] = sess
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


def _automate_session(session, name):
    screen = session.Screen
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

    # Clean slate every time: close whatever's open, then launch all fresh.
    _close_all_sessions()
    time.sleep(3)

    for name in session_names:
        os.startfile(os.path.join(location, file_by_name[name]))
    time.sleep(30)

    try:
        named_sessions = _attach_named_sessions(session_names)
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
        "message": (
            f"Closed all sessions and opened {len(session_names)} fresh. "
            f"Processed {len(results)} session(s). {sum(r['success'] for r in results)} succeeded."
        ),
    }
