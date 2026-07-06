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


def _attach_named_sessions(expected_names) -> dict:
    """
    Scan every EXTRA session (System.Sessions can accumulate stale/zombie
    entries whose underlying process is gone) and return {name: session}
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
            sess.Screen  # sanity check the session is actually alive
        except Exception:
            continue  # session reports a name but its Screen is dead too

        found[remaining[name]] = sess
        del remaining[name]

    return found


def _dismiss_save_prompt(timeout=5) -> bool:
    """
    Closing a disconnected session can pop a native 'Cannot save to file ...
    Would you like to save to a different file?' dialog (e.g. when the
    .rd3x profile lives under a read-only ProgramData path). That's a
    Windows dialog, not part of the EXTRA COM screen buffer, so find it and
    click 'No' so it doesn't block automation.
    """
    try:
        import win32gui
        import win32con
    except ImportError:
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        dialogs = []

        def _enum_top(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.GetClassName(hwnd) == "#32770":  # standard dialog class
                dialogs.append(hwnd)
            return True

        win32gui.EnumWindows(_enum_top, None)

        for hwnd in dialogs:
            no_buttons = []

            def _enum_child(child, _):
                if (
                    win32gui.GetClassName(child) == "Button"
                    and win32gui.GetWindowText(child).strip().upper() == "NO"
                ):
                    no_buttons.append(child)
                return True

            win32gui.EnumChildWindows(hwnd, _enum_child, None)
            if no_buttons:
                win32gui.SendMessage(no_buttons[0], win32con.BM_CLICK, 0, 0)
                return True

        time.sleep(0.25)

    return False


def _close_without_saving(session):
    """
    Close a session without the 'Cannot save to file' prompt blocking us.
    Prefers CloseEx(False) (explicit "don't save") if available; falls back
    to Close() + dismissing the native save-prompt dialog if it appears.
    """
    try:
        session.CloseEx(False)
        return
    except Exception:
        pass

    try:
        session.Close()
    except Exception:
        pass

    _dismiss_save_prompt()


def _ensure_connected(session, name, location, file_by_name, timeout=25):
    """
    If the session has lost its host connection ("Not connected to the
    host"), close it and relaunch its .rd3x profile fresh — there is no
    Connect()/reconnect method on the Session COM object, only Close/CloseEx.

    Returns (session, connected):
      - session may be a new COM object if a relaunch happened.
      - connected is False if it never came back within the timeout.
    If the Connected state can't even be read, we don't block on it.
    """
    try:
        connected = session.Connected
    except Exception:
        return session, True

    if connected:
        return session, True

    _close_without_saving(session)

    filename = file_by_name.get(name, f"{name}.rd3x")
    os.startfile(os.path.join(location, filename))

    for _ in range(timeout):
        time.sleep(1)
        fresh = _attach_named_sessions([name]).get(name)
        if fresh is None:
            continue
        try:
            if fresh.Connected:
                return fresh, True
        except Exception:
            return fresh, True

    return session, False


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
        named_sessions = _attach_named_sessions(session_names)
    except Exception as e:
        return {"success": False, "sessions": [], "message": f"Failed to attach to emulator sessions: {e}"}

    results = []
    for name in session_names:
        if name not in named_sessions:
            results.append({"name": name, "success": False, "message": "Session not available"})
            continue

        session, connected = _ensure_connected(named_sessions[name], name, location, file_by_name)
        if not connected:
            results.append({"name": name, "success": False, "message": "Session not connected to host and reconnect failed."})
            continue

        result = _automate_session(session, name)
        results.append(result)

    all_ok = all(r["success"] for r in results)
    return {
        "success": all_ok,
        "sessions": results,
        "message": f"{msg} Processed {len(results)} session(s). {sum(r['success'] for r in results)} succeeded.",
    }
