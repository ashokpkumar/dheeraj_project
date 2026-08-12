"""
NEW.LINE.UPDATE.RELEASE Macro — main registered function.
Ports cmdRun_Click (Macro/Main.txt) + Line_Update_Release /
ClaimDraft_SVCLn_Update / No_SVCLn_Update (Macro/oWauben.txt).

Data split, per the request:
  - CLAIM LEVEL INFO / SERVICE LINE INFO row data (columns A-AK on the
    original MN sheet) come from the DB/file — fetched by a separate
    function upstream in the pipeline and handed in as context['df'],
    one row per SERVICE LINE (see the column list in
    new_line_update_release_run_batch's docstring below).
  - Everything else — the MACRO SETTINGS control-panel cells/checkboxes
    from Macro/Main.txt (RLS CODE, LST RLS, PEND RSN, OPID, EOB/CK/DCI,
    PAYEE, INEL.CD FLD, APPLY UC/DPSV, CHG PROVIDER, REMOVE OI ELIG/AMT,
    RELEASE-IF-INEL-CODE, IGNORE PND CD, REPRICE %, CHANGE COND ONSET DT,
    APPLY INEL CD EXCEPTIONS, JUST RELEASE CLAIM, etc.) — is configurable
    through the rule engine via rule_code_ref_template.csv, keyed by a
    RULE column on each row, exactly like release_pend_macro.

Only REFLECTION/EXTRA is supported (no other ported macro in this codebase
implements the IBM PCOMM branch either).
"""

import csv
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

import pandas as pd

from rule_engine.registry import register_function
from rule_engine.functions.helpers import attach_emulator_sessions

from .utils import (
    data_entry_cps506_line_update, get_screen_id, load_line_update_reference,
    no_svcln_update, oop_claim, pf9_to_cps520, place_value, remove_value,
    rtn_pnd_code, send_enter, send_pf, update_hcfa_service_lines,
    update_ub_service_lines,
)


# ---------------------------------------------------------------------------
# Helper: load rule_code_ref CSV (mirrors release_pend_macro's loader)
# ---------------------------------------------------------------------------
def _load_rule_code_ref(path: str) -> dict:
    rules = {}
    if not path or not os.path.exists(path):
        return rules
    with open(path, newline="", encoding="utf-8-sig") as _f:
        for _row in csv.DictReader(_f):
            rule_name = (_row.get("rule") or "").strip().upper()
            if not rule_name:
                continue
            rules[rule_name] = {
                _k: (str(_v).strip() if _v is not None else "")
                for _k, _v in _row.items()
                if _k != "rule"
            }
    return rules


def _fmt_mmddyy(val) -> str:
    val = str(val or "").strip()
    if not val:
        return ""
    try:
        return pd.to_datetime(val).strftime("%m%d%y")
    except Exception:
        return val


# ---------------------------------------------------------------------------
# Per-claim body — ports Line_Update_Release
# ---------------------------------------------------------------------------
def _navigate_and_count_drafts(screen, claim_no: str):
    """Returns (ok, total_drafts, message). Mirrors the EntryPoint block."""
    for _attempt in range(3):
        if not pf9_to_cps520(screen, max_tries=15):
            # Case Else recovery (VBA's "i GJBB"/"GJBB" screen reset trick)
            send_pf(screen, 22)
            place_value(screen, "i GJBB", 31, 15)
            send_enter(screen)
            place_value(screen, "GJBB", 31, 15)
            send_enter(screen)
            send_pf(screen, 9)
            continue

        place_value(screen, claim_no, 8, 15)
        send_enter(screen)

        sid = get_screen_id(screen)
        if sid == "CPS515.01":
            send_pf(screen, 9)
            continue
        if sid == "CPS520.01":
            msg = (screen.GetString(31, 2, 60) or "").strip()
            return False, 0, msg or "CLAIM NOT FOUND"

        total_drafts = 0
        while True:
            for i in range(6, 20, 2):
                if not (screen.GetString(i, 2, 2) or "").strip():
                    break
                total_drafts += 1
            if "MORE DATA" in (screen.GetString(20, 2, 60) or "").upper():
                send_pf(screen, 11)
                continue
            break
        send_pf(screen, 9)
        return True, total_drafts, ""

    return False, 0, "SCREEN MAPPING ERROR"


def _process_line_update_claim(screen, claim_no: str, lines: list, settings: dict, ref: dict) -> dict:
    """
    Processes every draft of one claim. `lines` is the list of service-line
    dict rows (already filtered to this CLAIM_NO), mutated in place with
    `_STATUS` markers as they get matched/updated.
    """
    try:
        ok, total_drafts, msg = _navigate_and_count_drafts(screen, claim_no)
        if not ok:
            return {"CLAIM CONTROL #": claim_no, "MACRO STATUS": msg}

        just_release = settings.get("just_release_claim", "N") == "Y"

        if oop_claim(lines):
            return {"CLAIM CONTROL #": claim_no, "MACRO STATUS": "POSSIBLE OUT-OF-NETWORK CLAIM"}

        route_to_opid = str(lines[0].get("ROUTE_TO_OPID", "") or "").strip()
        new_prv_val = str(lines[0].get("NEW_PRV_VAL", "") or "").strip()

        lst_rls = settings.get("lst_rls", "Y")
        ignore_pnd_cd = settings.get("ignore_pnd_cd", "N") == "Y"
        pnd_cd_to_ignore = settings.get("pnd_cd_to_ignore", "")
        draft_sub_line_apply01 = settings.get("draft_sub_line_apply01", "N") == "Y"
        skip_no_update_check = settings.get("skip_no_update_check", "N") == "Y"
        release_if_inel_code = settings.get("release_if_inel_code", "")

        draft_no, pg_cur = 1, 1
        status_parts = []

        i = 1
        while i <= total_drafts:
            send_pf(screen, 9)
            place_value(screen, claim_no, 8, 15)
            send_enter(screen)

            if draft_no > 7:
                draft_no = 1
                pg_cur += 1
            if pg_cur > 1:
                for _ in range(pg_cur - 1):
                    send_pf(screen, 11)

            if not just_release:
                if lst_rls == "Y":
                    if ignore_pnd_cd:
                        if not pnd_cd_to_ignore:
                            status_parts.append(f"DRAFT:{i}:PEND CODE TO IGNORE IS MISSING. MACRO ABORT")
                            break
                        if rtn_pnd_code(screen, f"{draft_no:02d}") == pnd_cd_to_ignore:
                            draft_no += 1
                            i += 1
                            continue  # NextDraft
                        place_value(screen, f"{draft_no:02d}", 3, 26)
                    else:
                        place_value(screen, "01", 3, 26)
                else:
                    if draft_sub_line_apply01:
                        place_value(screen, "01", 3, 26)
                    else:
                        place_value(screen, f"{draft_no:02d}", 3, 26)

            send_enter(screen)

            if not just_release and settings.get("chg_provider", "N") == "Y":
                place_value(screen, "X", 29, 26)
                send_enter(screen)
                remove_value(screen, 3, 27)
                place_value(screen, settings.get("prv_zip", ""), 5, 69)
                place_value(screen, settings.get("prv_int_nbr", ""), 7, 30)
                send_enter(screen)
                if get_screen_id(screen) != "CPS310.01":
                    status_parts.append(f"DRAFT:{i}:PROVIDER CHANGE FAILED.")
                    break

            send_enter(screen)

            claim_type = None
            if not just_release:
                sid = get_screen_id(screen)
                if sid == "CPS920.01":
                    send_enter(screen)
                    status_parts.append(f"DRAFT:{i}:NOT RELEASED.{(screen.GetString(31, 2, 60) or '').strip()}")
                    break
                if sid == "BLX2460.01":
                    claim_type = "UB"
                    if settings.get("remove_prv", "N") == "Y":
                        remove_value(screen, 22, 6)
                    place_value(screen, new_prv_val, 22, 6)
                    if settings.get("inel2_option", "") == "REMOVE INEL2 AMTCD":
                        for j in range(12, 16):
                            remove_value(screen, j, 18)
                            remove_value(screen, j, 30)
                    if settings.get("rem_oi_elig_amt", "N") == "Y":
                        for j in range(18, 22):
                            remove_value(screen, j, 2)
                            remove_value(screen, j, 14)
                            remove_value(screen, j, 26)
                    if settings.get("apply_uc", "Y") == "Y":
                        place_value(screen, "X", 29, 71)
                elif sid == "CPS450.01":
                    claim_type = "HCFA"
                    if settings.get("remove_prv", "N") == "Y":
                        remove_value(screen, 26, 9)
                    place_value(screen, new_prv_val, 26, 9)
                    if settings.get("inel2_option", "") == "REMOVE INEL2 AMTCD":
                        for j in range(14, 18):
                            remove_value(screen, j, 18)
                            remove_value(screen, j, 30)
                    if settings.get("rem_oi_elig_amt", "N") == "Y":
                        for j in range(20, 24):
                            remove_value(screen, j, 4)
                            remove_value(screen, j, 16)
                            remove_value(screen, j, 28)
                    if settings.get("apply_uc", "Y") == "Y":
                        place_value(screen, "X", 29, 69)
                else:
                    status_parts.append(f"DRAFT:{i}:SCREEN NOT MAPPED.")
                    break
            else:
                sid = get_screen_id(screen)
                claim_type = "UB" if sid == "BLX2460.01" else ("HCFA" if sid == "CPS450.01" else None)

            # -- service line matching / update --
            # NOTE: unlike most other failure points in this claim (which
            # abort the whole claim via "GoTo NextRw"), the VBA's own
            # "GoTo NextRw" here is commented out ('GoTo NextRw) — a
            # ClaimDraft_SVCLn_Update failure just records the message and
            # moves on to the NEXT DRAFT (no CPS506 release is attempted
            # for this draft), rather than aborting the claim. Preserved
            # as-is below via `attempt_release`.
            attempt_release = True
            if not just_release:
                unmatched = [ln for ln in lines if not ln.get("_STATUS")]
                if not skip_no_update_check and no_svcln_update(screen, release_if_inel_code, claim_type):
                    send_enter(screen)
                else:
                    if claim_type == "UB":
                        matched, svc_msg = update_ub_service_lines(
                            screen, unmatched, settings, ref["ub_inelcd"], ref["exception_inel_codes"]
                        )
                    elif claim_type == "HCFA":
                        matched, svc_msg = update_hcfa_service_lines(
                            screen, unmatched, settings, ref["hcfa_inelcd"], ref["exception_inel_codes"]
                        )
                    else:
                        matched, svc_msg = False, "SCREEN NOT MAPPED."
                    if not matched:
                        status_parts.append(f"DRAFT:{i}:{svc_msg or 'FAILED'}")
                        attempt_release = False
                    else:
                        send_enter(screen)

            if not attempt_release:
                draft_no += 1
                i += 1
                continue

            # -- rTry: resolve intermediate screens until CPS506.01 --
            aborted = False
            for _rtry in range(10):
                sid = get_screen_id(screen)

                if sid == "BLX2460.01":
                    if claim_type == "HCFA":
                        send_pf(screen, 8)
                        place_value(screen, "450", 2, 37)
                        send_enter(screen)
                        if settings.get("apply_dpsv", "Y") != "N":
                            place_value(screen, "X", 29, 76)
                        send_enter(screen)
                        continue
                    msg31 = (screen.GetString(31, 2, 70) or "").strip()
                    msg30 = (screen.GetString(30, 2, 70) or "").strip()
                    exc = msg31 or msg30
                    if "PRIOR TO CND ONSET" in exc and settings.get("change_cond_onset_dt", "N") == "Y":
                        send_pf(screen, 8)
                        place_value(screen, "910", 2, 37)
                        send_enter(screen)
                        place_value(screen, _fmt_mmddyy(settings.get("new_cond_onset_dt", "")), 5, 24)
                        send_enter(screen)
                        continue
                    status_parts.append(f"DRAFT:{i}:{exc}")
                    aborted = True
                    break

                if sid == "CPS450.01":
                    if claim_type == "UB":
                        send_pf(screen, 8)
                        place_value(screen, "460", 2, 37)
                        send_enter(screen)
                        if settings.get("apply_dpsv", "Y") != "N":
                            place_value(screen, "X", 29, 78)
                        send_enter(screen)
                        continue
                    msg31 = (screen.GetString(31, 2, 70) or "").strip()
                    msg30 = (screen.GetString(30, 2, 70) or "").strip()
                    exc = msg31 or msg30
                    if "PRIOR TO CND ONSET" in exc and settings.get("change_cond_onset_dt", "N") == "Y":
                        send_pf(screen, 8)
                        place_value(screen, "910", 2, 37)
                        send_enter(screen)
                        place_value(screen, _fmt_mmddyy(settings.get("new_cond_onset_dt", "")), 5, 24)
                        send_enter(screen)
                        continue
                    status_parts.append(f"DRAFT:{i}:{exc}")
                    aborted = True
                    break

                if sid == "CPS445.01":
                    send_enter(screen)
                    if claim_type == "HCFA" and get_screen_id(screen) == "BLX2460.01":
                        send_pf(screen, 8)
                        place_value(screen, "450", 2, 37)
                        send_enter(screen)
                    if claim_type == "UB" and get_screen_id(screen) == "CPS450.01":
                        send_pf(screen, 8)
                        place_value(screen, "460", 2, 37)
                        send_enter(screen)
                    place_value(screen, "X", 29, 76 if claim_type == "HCFA" else 78)
                    send_enter(screen)
                    continue

                if sid == "CPS506.01":
                    if (screen.GetString(7, 8, 1) or "").strip() == "1" and str(settings.get("payee", "0")) == "0":
                        # Mirrors "GoTo NextDraft" — skip this draft (no CPS506
                        # data entry attempted) and move on to the next one.
                        status_parts.append(f"DRAFT:{i} CANCELLED: CHANGE PAYEE TO 1")
                        break
                    data_entry_cps506_line_update(screen, {"ROUTE_TO_OPID": route_to_opid}, settings)
                    if settings.get("show_confirmation", "N") == "Y":
                        pass  # SHOW CONFIRMATION was an interactive VBA MsgBox — no-op in batch mode
                    send_enter(screen)
                    if get_screen_id(screen) == "CPS506.01":
                        msg31 = (screen.GetString(31, 2, 70) or "").strip()
                        msg2 = (screen.GetString(2, 2, 48) or "").strip()
                        rel_word = "RELEASED" if lst_rls == "Y" else "PENDED"
                        status_parts.append(f"NOT {rel_word}:DRAFT:{i}:{msg2}:{msg31}".strip(": "))
                        aborted = True
                    else:
                        rel_word = "RELEASED" if lst_rls == "Y" else "PENDED"
                        status_parts.append(f"{rel_word}:DRAFT:{i}")
                    break

                status_parts.append(f"DRAFT:{i}:SCREEN MAPPING ERROR")
                aborted = True
                break
            else:
                status_parts.append(f"DRAFT:{i}:TOO MANY SCREEN RETRIES")
                aborted = True

            if aborted:
                break

            draft_no += 1
            i += 1

        macro_status = " | ".join(status_parts) if status_parts else "DONE."
        return {"CLAIM CONTROL #": claim_no, "MACRO STATUS": macro_status}

    except Exception as exc:
        traceback.print_exc()
        return {"CLAIM CONTROL #": claim_no, "MACRO STATUS": f"EXCEPTION: {type(exc).__name__}: {exc}"}
    finally:
        try:
            send_pf(screen, 9)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main batch function
# ---------------------------------------------------------------------------
@register_function(
    name="new_line_update_release_run_batch",
    tag="New Line Update Release",
    color="#e65100",
    inputs=[
        {"name": "reference_path", "type": "str", "default": ""},
        {"name": "rule_code_ref_path", "type": "str", "default": ""},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "result", "type": "list"},
    ],
)
def new_line_update_release_run_batch(reference_path: str, rule_code_ref_path: str = "", context=None):
    """
    Main NEW.LINE.UPDATE.RELEASE batch processor. Port of cmdRun_Click ->
    Line_Update_Release. Settings are driven entirely by rule_code_ref_path
    (see rule_code_ref_template.csv) — each row in context['df'] must carry
    a RULE column matching the 'rule' column in that CSV.

    context['df'] is expected to be one row per SERVICE LINE (fetched
    upstream, e.g. by a separate DB/file-fetch function), with these
    columns (mirrors Macro/oColumnMapping):
      CLAIM_NO, RULE, ROUTE_TO_OPID, NEW_PRV_VAL,               (claim-level, carried on every line of the claim)
      BGN_SV_DT, CPT, LINE_CHG_AMT, UNITS, MOD01, MOD02, MOD03, (match criteria — blank = don't care)
      AP, NEW_INEL1_AMOUNT, NEW_INEL1_CD, NEW_INEL2_AMOUNT, NEW_INEL2_CD,
      NEW_MOD01, NEW_MOD02, NEW_MOD03, SMB_ADJ_AMT, SMB_ADJ_REASON,
      OI_ELIG_AMT, OI_PAID_AMT, OI_TYPE, BU, IU, OC, PROV_RATE,
      NEW_BGN, NEW_END, NEW_TOS, NEW_CHRG_AMT, BN_QTY, BN_AMT
    OI_ELIG_AMT/OI_PAID_AMT and NEW_INEL1_AMOUNT can instead be populated by
    chaining new_line_update_medicare_oi_calc / new_line_update_mru_repricing_calc
    ahead of this function in the pipeline.
    """
    print("[new_line_update_release_run_batch] Starting...")

    if context is None:
        return {"success": False, "result": [], "error": "context is None"}

    df = context.get("df")
    if df is None:
        return {"success": False, "result": [], "error": "context['df'] is None"}
    if df.empty:
        return {"success": True, "result": []}

    print(f"[new_line_update_release_run_batch] {len(df)} rows to process. Columns: {list(df.columns)}")

    try:
        ref = load_line_update_reference(reference_path) if reference_path else {
            "hcfa_inelcd": set(), "ub_inelcd": set(), "exception_inel_codes": set(),
            "mru_innetwork_pos": set(), "med_calc": {}, "mru_calc": {},
        }
    except Exception as _e:
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"load_line_update_reference failed: {_e}"}

    try:
        rule_ref = _load_rule_code_ref(rule_code_ref_path) if rule_code_ref_path else {}
        print(f"[new_line_update_release_run_batch] Loaded {len(rule_ref)} rules: {list(rule_ref.keys())}")
    except Exception as _e:
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"_load_rule_code_ref failed: {_e}"}

    rows = [{k: ("" if v is None else str(v).strip()) for k, v in r.items()} for r in df.to_dict("records")]

    claims = {}
    claim_order = []
    for row in rows:
        claim_no = str(row.get("CLAIM_NO", "")).strip()
        if not claim_no:
            continue
        if claim_no not in claims:
            claims[claim_no] = []
            claim_order.append(claim_no)
        claims[claim_no].append(row)

    try:
        sessions = attach_emulator_sessions(n=4)
        print(f"[new_line_update_release_run_batch] Attached {len(sessions)} emulator session(s).")
    except Exception as _e:
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"Emulator connection failed: {_e}"}

    worker_count = min(4, len(sessions))
    print(f"[new_line_update_release_run_batch] Using {worker_count} emulator session(s) for {len(claim_order)} claim(s).")

    indexed_claims = list(enumerate(claim_order))
    buckets = [indexed_claims[i::worker_count] for i in range(worker_count)]

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

            for pos, claim_no in items:
                lines = claims[claim_no]
                rule_key = str(lines[0].get("RULE", "")).strip().upper()
                if not rule_key:
                    res = {"CLAIM CONTROL #": claim_no, "MACRO STATUS": "SKIPPED: RULE column is empty"}
                elif rule_key not in rule_ref:
                    res = {"CLAIM CONTROL #": claim_no, "MACRO STATUS": f"SKIPPED: RULE {rule_key!r} not found in rule CSV"}
                else:
                    settings = rule_ref[rule_key]
                    try:
                        res = _process_line_update_claim(worker_screen, claim_no, lines, settings, ref)
                    except Exception as exc:
                        traceback.print_exc()
                        res = {"CLAIM CONTROL #": claim_no, "MACRO STATUS": f"EXCEPTION: {type(exc).__name__}: {exc}"}
                out_q.put((pos, res))
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for i in range(worker_count):
            pool.submit(_worker, i, buckets[i])

        results = [None] * len(claim_order)
        collected = 0
        while collected < len(claim_order):
            pos, res = out_q.get()
            results[pos] = res
            collected += 1

    print(f"[new_line_update_release_run_batch] Done. Processed {len(results)}/{len(claim_order)} claims.")
    return {"success": True, "result": results}
