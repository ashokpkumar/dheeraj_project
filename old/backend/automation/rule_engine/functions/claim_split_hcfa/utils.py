"""
Claim Split HCFA — shared mainframe-screen primitives.

Ports the small helper subs at the top of oShared.txt (PLACEVALUE,
REMOVEVALUE, INCORRECTSCREEN). Deliberately self-contained (not imported
from release_pend_macro/utils.py) — same convention release_pend_macro
itself follows: each function package owns its own copy of these primitives
rather than sharing one across packages, only `register_function` and
`attach_emulator_sessions` come from the shared `rule_engine` package.
"""


def wait_ready(screen):
    while screen.OIA.Xstatus != 0:
        pass


def get_screen_id(screen) -> str:
    return (screen.GetString(1, 2, 11) or "").strip()


def place_value(screen, val, r: int, c: int):
    """Mirrors PLACEVALUE VBA — no-op on blank/None, same as the VBA's
    `If Len(Trim(val)) < 1 Then Exit Function` guard."""
    val = ("" if val is None else str(val)).strip()
    if not val:
        return
    wait_ready(screen)
    screen.MoveTo(r, c)
    wait_ready(screen)
    screen.SendKeys("<EraseEof>")
    wait_ready(screen)
    screen.PutString(val, r, c)
    wait_ready(screen)


def remove_value(screen, r: int, c: int):
    """Mirrors REMOVEVALUE VBA."""
    wait_ready(screen)
    screen.MoveTo(r, c)
    wait_ready(screen)
    screen.SendKeys("<EraseEof>")
    wait_ready(screen)


def send_enter(screen):
    screen.SendKeys("<Enter>")
    wait_ready(screen)


def send_pf(screen, n: int):
    screen.SendKeys(f"<Pf{n}>")
    wait_ready(screen)


def is_screen(screen, expected_id: str) -> bool:
    """
    Mirrors INCORRECTSCREEN VBA. Kept the same true-when-matching behavior
    as the original (the VBA name is a misnomer — every call site reads it
    as "is the current screen this one", e.g.
    `If INCORRECTSCREEN("CPS450.01", 1, 2, 11) Then` — so this port is named
    for what it actually does instead of copying the confusing name).
    The VBA's (R, C, L) args were always (1, 2, 11) at every call site, so
    they're fixed here rather than threaded through as parameters.
    """
    wait_ready(screen)
    return get_screen_id(screen) == expected_id


def normalize_edit_msg(text: str) -> str:
    """Mirrors NORMALIZE_EDIT_MSG VBA — collapse whitespace, uppercase, trim."""
    return " ".join((text or "").split()).upper()
