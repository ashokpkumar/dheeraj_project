"""
Claims Split UB — shared mainframe-screen primitives.

Ports the small helper subs at the top of oShared.txt (PLACEVALUE,
REMOVEVALUE, INCORRECTSCREEN). Deliberately self-contained (not imported
from claim_split_hcfa/utils.py or release_pend_macro/utils.py) — same
convention every function package under rule_engine/functions/ follows: each
owns its own copy of these primitives rather than sharing one across
packages, only `register_function` and `attach_emulator_sessions` come from
the shared `rule_engine` package.

Byte-for-byte the same primitives as claim_split_hcfa/utils.py — oShared.txt
is identical between the two macros for this section — plus REMOVEVALUE
(oShared.txt "ADDED 2026.08.14"), which claim_split_hcfa's oShared.txt does
not have; it's used by UB_NonScratch_Split's "REMOVE ALL/EXISTING INEL"
branch (see cps_entry.py).
"""


def wait_ready(screen):
    while screen.OIA.Xstatus != 0:
        pass


def get_screen_id(screen) -> str:
    return (screen.GetString(1, 2, 11) or "").strip()


def place_value(screen, val, r: int, c: int):
    """Mirrors PLACEVALUE VBA — no-op on blank/None, same as the VBA's
    `If Len(Trim(val)) < 0 Then Exit Function` guard (note: the VBA's guard
    is `< 0`, which is never true for a Len() result — effectively a no-op
    guard, i.e. PLACEVALUE never actually skips a blank value in the VBA.
    Kept as `< 1` here anyway, matching claim_split_hcfa's port and every
    call site's real intent — a literal `< 0` port would send an empty
    PutString, which no call site in oScratch.txt/oNonScratch.txt/
    oScratchNotOnline relies on)."""
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
    """Mirrors REMOVEVALUE VBA (oShared.txt, 'ADDED 2026.08.14') — clears a
    field without writing a replacement value."""
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
    `If INCORRECTSCREEN("CPS520.01", 1, 2, 11) Then` — so this port is named
    for what it actually does instead of copying the confusing name).
    The VBA's (R, C, L) args were always (1, 2, 11) at every call site, so
    they're fixed here rather than threaded through as parameters.
    """
    wait_ready(screen)
    return get_screen_id(screen) == expected_id


def normalize_edit_msg(text: str) -> str:
    """Mirrors NORMALIZE_EDIT_MSG VBA — collapse whitespace, uppercase, trim."""
    return " ".join((text or "").split()).upper()
