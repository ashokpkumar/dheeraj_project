"""
Diagnostic: figure out which Session/Screen COM properties are safely
readable on this machine, so we can identify open emulator sessions
by name without hitting the 'Failed to connect to an IPC Port' error.

Run with your WAUBEN* emulators already open:
    python diagnose_sessions.py
"""
import win32com.client
import pythoncom

pythoncom.CoInitialize()
system = win32com.client.Dispatch("EXTRA.System")
sessions = system.Sessions
print(f"Sessions.Count = {sessions.Count}\n")

candidate_props = [
    "Name",
    "Description",
    "Connected",
    "Path",
    "SessionFile",
    "FileName",
    "Caption",
]

for i in range(1, sessions.Count + 1):
    sess = sessions.Item(i)
    print(f"--- Session index {i} ---")
    for prop in candidate_props:
        try:
            val = getattr(sess, prop)
            print(f"  Session.{prop} = {val!r}")
        except Exception as e:
            print(f"  Session.{prop} -> ERROR: {e}")

    # Try the same candidates one level down, on Screen
    try:
        screen = sess.Screen
        for prop in candidate_props + ["WindowHandle", "hWnd", "WindowState"]:
            try:
                val = getattr(screen, prop)
                print(f"  Screen.{prop} = {val!r}")
            except Exception as e:
                pass  # skip noise, Screen mostly won't have these
    except Exception as e:
        print(f"  Screen -> ERROR: {e}")
    print()

# Cross-check with actual OS window titles, in case that's the more
# reliable path (each session may be its own top-level window).
try:
    import win32gui

    print("--- Top-level windows with 'WAUBEN' or 'EXTRA'/'Reflection' in the title ---")

    def _cb(hwnd, results):
        title = win32gui.GetWindowText(hwnd)
        if title and win32gui.IsWindowVisible(hwnd):
            results.append((hwnd, title))
        return True

    found = []
    win32gui.EnumWindows(_cb, found)
    for hwnd, title in found:
        if any(k in title.upper() for k in ("WAUBEN", "EXTRA", "REFLECTION")):
            print(f"  hwnd={hwnd}  title={title!r}")
except ImportError:
    print("win32gui not available — skipping window-title cross-check")
