"""
Same Day Reversal macro — main registered function.
Ports cmdRun_Click (Same_Day_Reversal/Main.txt) and Draft_Reveral_9994
(Same_Day_Reversal/oIShared.txt).
"""

import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from queue import Queue

from rule_engine.registry import register_function
from rule_engine.functions.helpers import attach_emulator_sessions

from .utils import (
    get_screen_id, in_correct_screen, place_value,
    run_claim_type_reversal, send_enter, send_pf,
)


# ---------------------------------------------------------------------------
# Draft_Reveral_9994 port
# ---------------------------------------------------------------------------
def draft_reversal_9994(screen, cert_id: str, ccn: str, bg_sv_dt: str, max_entry_attempts: int = 5) -> dict:
    """
    Port of Draft_Reveral_9994. Given a cert id, CCN and same-day-reversal
    date, reverses the matching draft(s) on the mainframe. Returns
    {'CLAIM_TYPE', 'DS_COUNT', 'STATUS'} mirroring sheet columns C / E / G.

    The VBA 'Case False' branch (not on BLX112.01) retries EntryPoint
    unconditionally via GoTo, which can loop forever if the recovery
    navigation never lands on BLX112.01; that's bounded here to
    max_entry_attempts instead.
    """
    if not (bg_sv_dt or "").strip():
        bg_sv_dt = datetime.now().strftime("%m%d%y")

    result = {"CLAIM_TYPE": "", "DS_COUNT": 0, "STATUS": ""}

    try:
        for _attempt in range(max_entry_attempts):
            if in_correct_screen(screen, "BLX112.01", 1, 71, 10):
                place_value(screen, cert_id, 9, 15)
                place_value(screen, bg_sv_dt, 12, 15)
                send_enter(screen)

                if not in_correct_screen(screen, "BLX106.01", 1, 72, 10):
                    result["STATUS"] = "MEMBER NOT FOUND"
                    return result

                send_enter(screen)
                place_value(screen, "00", 2, 6)  # Default 00
                send_enter(screen)
                send_pf(screen, 7)
                place_value(screen, ccn, 13, 45)
                place_value(screen, "x", 16, 45)  # Search all family
                send_enter(screen)

                screen_id = get_screen_id(screen)
                if screen_id == "BLX143.01":
                    result["STATUS"] = run_claim_type_reversal(screen, "HCFA", ccn, result)
                elif screen_id == "BLX143":
                    result["STATUS"] = run_claim_type_reversal(screen, "UB", ccn, result)
                else:
                    result["STATUS"] = "BLX143.01: UNABLE TO MAP SERVICE DISPLAY"
                return result

            # 'Case False' recovery navigation — not on BLX112.01, drive back to it
            send_pf(screen, 22)
            place_value(screen, "i GJBB", 31, 15)
            send_enter(screen)
            place_value(screen, "GJBB", 31, 15)
            send_enter(screen)
            send_pf(screen, 9)
            # retries EntryPoint

        result["STATUS"] = "UNABLE TO REACH BLX112.01 AFTER RETRIES"
        return result
    finally:
        send_pf(screen, 9)


def _process_reversal_row(screen, row: dict) -> dict:
    """Per-row body of same_day_reversal_run_batch."""
    ccn = (row.get("CCN", "") or "").strip()
    cert_id = (row.get("CERT_ID", "") or "").strip()
    bg_sv_dt = (row.get("BG_SV_DT", "") or "").strip()

    if not ccn or not cert_id:
        print(f"[{ccn or cert_id}] WARNING: CCN/CERT_ID missing on row — skipping")
        return {"CLAIM CONTROL #": ccn, "MACRO STATUS": "SKIPPED: empty CCN/CERT_ID", "CLAIM_TYPE": "", "DS_COUNT": 0}

    print(f"[{ccn}] CERT_ID={cert_id!r} BG_SV_DT={bg_sv_dt!r} — starting draft reversal")
    try:
        res = draft_reversal_9994(screen, cert_id, ccn, bg_sv_dt)
    except Exception as exc:
        print(f"[{ccn}] EXCEPTION: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        try:
            send_pf(screen, 9)
        except Exception:
            pass
        return {"CLAIM CONTROL #": ccn, "MACRO STATUS": f"EXCEPTION: {type(exc).__name__}: {exc}", "CLAIM_TYPE": "", "DS_COUNT": 0}

    print(f"[{ccn}] RESULT: {res['STATUS']!r}")
    return {
        "CLAIM CONTROL #": ccn,
        "MACRO STATUS": res["STATUS"],
        "CLAIM_TYPE": res["CLAIM_TYPE"],
        "DS_COUNT": res["DS_COUNT"],
    }


# ---------------------------------------------------------------------------
# Main batch function
# ---------------------------------------------------------------------------
@register_function(
    name="same_day_reversal_run_batch",
    tag="Same Day Reversal",
    color="#6a1b9a",
    inputs=[],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "result", "type": "list"},
    ],
)
def same_day_reversal_run_batch(context=None):
    """
    Main same-day (draft) reversal batch processor. Port of cmdRun_Click,
    which drove Draft_Reveral_9994 once per sheet row. Expects
    context['df'] rows with CCN, CERT_ID, BG_SV_DT columns (mirrors sheet
    columns A / B / D). Rows are independent, so they're processed in
    parallel across up to 4 emulator sessions round-robin, same pattern as
    release_pend_macro / OI_YES_NO.
    """
    print("[same_day_reversal_run_batch] Starting...")

    if context is None:
        print("[same_day_reversal_run_batch] ERROR: context is None")
        return {"success": False, "result": [], "error": "context is None"}

    df = context.get("df")

    if df is None:
        print("[same_day_reversal_run_batch] ERROR: context['df'] is None — no DataFrame passed")
        return {"success": False, "result": [], "error": "context['df'] is None"}

    if df.empty:
        print("[same_day_reversal_run_batch] WARNING: DataFrame is empty — nothing to process")
        return {"success": True, "result": []}

    print(f"[same_day_reversal_run_batch] {len(df)} rows to process. Columns: {list(df.columns)}")

    _df_cols_upper = [c.upper() for c in df.columns]
    for _col in ("CCN", "CERT_ID", "BG_SV_DT"):
        if _col not in _df_cols_upper:
            print(f"[same_day_reversal_run_batch] WARNING: Expected column '{_col}' not found — check your DataFrame")

    print("[same_day_reversal_run_batch] Connecting to EXTRA.System...")
    try:
        sessions = attach_emulator_sessions(n=4)
        print(f"[same_day_reversal_run_batch] Attached {len(sessions)} emulator session(s). "
              f"Initial screen on session 1: {get_screen_id(sessions[0].Screen)!r}")
    except Exception as _e:
        print(f"[same_day_reversal_run_batch] ERROR connecting to emulator: {_e}")
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"Emulator connection failed: {_e}"}

    worker_count = min(4, len(sessions))
    print(f"[same_day_reversal_run_batch] Using {worker_count} emulator session(s) for {len(df)} row(s).")

    # (position, row) so results can be reassembled in original order; split
    # evenly round-robin across all attached sessions — rows are independent
    # (no cross-row state like release_pend's cert_no_skip).
    indexed_rows = []
    for pos, (_, row_series) in enumerate(df.iterrows()):
        row = {k.upper(): (str(v).strip() if v is not None else "") for k, v in row_series.to_dict().items()}
        indexed_rows.append((pos, row))
    buckets = [indexed_rows[i::worker_count] for i in range(worker_count)]

    out_q = Queue()

    def _worker(worker_idx, items):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            worker_session = sessions[worker_idx]
            worker_screen = worker_session.Screen
            try:
                worker_screen.WaitHostQuiet(2000)
            except Exception:
                pass

            for pos, row in items:
                ccn = row.get("CCN", "")
                try:
                    res = _process_reversal_row(worker_screen, row)
                except Exception as exc:
                    print(f"[same_day_reversal_run_batch] Worker {worker_idx} error on {ccn}: {exc}")
                    traceback.print_exc()
                    res = {"CLAIM CONTROL #": ccn, "MACRO STATUS": f"EXCEPTION: {type(exc).__name__}: {exc}"}
                out_q.put((pos, res))
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for i in range(worker_count):
            pool.submit(_worker, i, buckets[i])

        results = [None] * len(df)
        collected = 0
        while collected < len(df):
            pos, res = out_q.get()
            results[pos] = res
            collected += 1

    print(f"\n[same_day_reversal_run_batch] Done. Processed {len(results)}/{len(df)} claims.")
    return {"success": True, "result": results}
