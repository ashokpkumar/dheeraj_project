import os
import time
import win32com.client
from rule_engine.registry import register_function

REFLECTION_PROGID = "Attachmate_Reflection_Objects.ApplicationObject"

# IBM 3270 ControlKeyCode for Enter/Transmit — verify against your Reflection Desktop version
ENTER_KEY = 1009


# ---------------------------------------------------------------------------
# COM helpers
# ---------------------------------------------------------------------------

def _get_reflection_app(retries=15, interval=2):
    """Wait for Reflection Desktop to register its COM object."""
    for _ in range(retries):
        try:
            return win32com.client.GetActiveObject(REFLECTION_PROGID)
        except Exception:
            time.sleep(interval)
    raise RuntimeError("Could not connect to Reflection Desktop via COM")


def _build_session_map(app, expected_names):
    """
    Return {session_name: terminal} for all open sessions whose name
    matches one of the expected rd3x basenames (case-insensitive).
    Retries for up to 30 s to allow slow session startup.
    """
    deadline = time.time() + 30
    while time.time() < deadline:
        found = {}
        for i in range(1, app.Sessions.Count + 1):
            session = app.Sessions.Item(i)
            base = session.Name.strip()
            for name in expected_names:
                if name.lower() == base.lower():
                    found[name] = session.Control
                    break
        if len(found) == len(expected_names):
            return found
        time.sleep(2)
    # Return whatever we have even if incomplete
    return found


# ---------------------------------------------------------------------------
# Screen helpers
# ---------------------------------------------------------------------------

def _read(terminal, row, col, length):
    return terminal.Screen.GetText(row, col, length).strip()


def _wait_for(terminal, row, col, length, keyword, timeout=20):
    for _ in range(timeout):
        if keyword.upper() in _read(terminal, row, col, length).upper():
            return True
        time.sleep(1)
    return False


def _type_at(terminal, row, col, text):
    terminal.Screen.MoveCursorTo(row, col)
    terminal.Screen.SendKeys(text)


def _enter(terminal):
    terminal.Screen.SendControlKey(ENTER_KEY)


# ---------------------------------------------------------------------------
# Navigation steps
# ---------------------------------------------------------------------------

def _step_entry_screen(terminal):
    """Confirm UHC0010 at (2,1), type UMR at (3,1), press Enter."""
    if not _wait_for(terminal, 2, 1, 27, "UHC0010"):
        return False, "Entry screen not detected — 'UHC0010' not found at (2,1)"
    _type_at(terminal, 3, 1, "UMR")
    _enter(terminal)
    return True, "Entry screen OK"


def _step_login_screen(terminal):
    """Confirm Userid at (16,5), fill credentials, press Enter, confirm TPX MENU."""
    if not _wait_for(terminal, 16, 5, 6, "Userid"):
        return False, "Login screen not detected — 'Userid' not found at (16,5)"
    _type_at(terminal, 16, 20, "RAUWTVW")
    _type_at(terminal, 17, 20, "RAJ$#2DP")
    _enter(terminal)
    if not _wait_for(terminal, 1, 25, 8, "TPX MENU"):
        return False, "TPX MENU not confirmed after login"
    return True, "Login screen OK"


def _step_tpx_menu(terminal):
    """Confirm TPX MENU at (1,25), Enter at (18,4), type GJBB at (1,1), Enter, confirm CPS515.01."""
    if not _wait_for(terminal, 1, 25, 8, "TPX MENU"):
        return False, "TPX MENU not detected at (1,25)"
    _type_at(terminal, 18, 4, "")   # move cursor to (18,4)
    _enter(terminal)
    time.sleep(1)
    _type_at(terminal, 1, 1, "GJBB")
    _enter(terminal)
    if not _wait_for(terminal, 1, 2, 9, "CPS515.01"):
        return False, "Claim screen not reached — 'CPS515.01' not found at (1,2)"
    return True, "Claim main screen reached"


def _automate_session(terminal, name):
    for step_fn in (_step_entry_screen, _step_login_screen, _step_tpx_menu):
        ok, msg = step_fn(terminal)
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

    # Open every session file
    for filename in rd3x_files:
        os.startfile(os.path.join(location, filename))

    # Connect to Reflection Desktop COM
    try:
        app = _get_reflection_app()
    except RuntimeError as e:
        return {"success": False, "sessions": [], "message": str(e)}

    # Build name -> terminal map, matched by rd3x basename
    session_names = [os.path.splitext(f)[0] for f in rd3x_files]
    session_map = _build_session_map(app, session_names)

    results = []
    for name in session_names:
        if name not in session_map:
            results.append({"name": name, "success": False, "message": "Session not found in Reflection Desktop"})
            continue
        result = _automate_session(session_map[name], name)
        results.append(result)

    all_ok = all(r["success"] for r in results)
    return {
        "success": all_ok,
        "sessions": results,
        "message": f"Processed {len(results)} session(s). "
                   f"{sum(r['success'] for r in results)} succeeded.",
    }
