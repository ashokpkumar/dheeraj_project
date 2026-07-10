"""
Release / Pend Macro — main registered functions.
Ports Release_or_Pend_Claim and Get_Claim_Details from Modules_oShared.txt.
"""

import csv
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from rule_engine.registry import register_function
from rule_engine.functions.helpers import attach_emulator_sessions

from .hcfa import hcfa_data_entry
from .tod import tod_update
from .ub import ub_data_entry, ub_per_diem_process
from .utils import (
    add_condition_note, apply_ineligibility_codes,
    get_screen_id, load_code_refs, place_value,
    place_new_csr_note, remove_value, send_enter, send_pf,
    update_condition_afv, wait_ready,
)


# ---------------------------------------------------------------------------
# Helper: load rule_code_ref CSV
# ---------------------------------------------------------------------------
def _load_rule_code_ref(path: str) -> dict:
    """
    Reads the rule code ref CSV keyed by the 'rule' column (case-insensitive).
    Each value is a plain dict of the CSV columns for that row.
    """
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


# ---------------------------------------------------------------------------
# Main batch function
# ---------------------------------------------------------------------------
@register_function(
    name="release_pend_run_batch",
    tag="Release Pend Macro",
    color="#2e7d32",
    inputs=[
        {"name": "dx_code_ref_path",   "type": "str", "default": ""},
        {"name": "rule_code_ref_path", "type": "str", "default": ""},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "result",  "type": "list"},
    ],
)
def release_pend_run_batch(
    dx_code_ref_path: str,
    rule_code_ref_path: str = "",
    context=None,
):
    """
    Main release/pend batch processor.
    Settings are driven entirely by rule_code_ref_path CSV.  Each row in
    context['df'] must have a RULE column whose value matches the 'rule'
    column in the CSV.  Falls back to _SETTING_DEFAULTS when no match found.
    new_ap_cd / new_prv_cd from the CSV are seeded into the claim row so
    downstream entry functions can read them via row.get('NEW_AP_CD') etc.
    """
    # ── Startup validation ────────────────────────────────────────────────
    print("[release_pend_run_batch] Starting...")

    if context is None:
        print("[release_pend_run_batch] ERROR: context is None")
        return {"success": False, "result": [], "error": "context is None"}

    df = context.get("df")

    if df is None:
        print("[release_pend_run_batch] ERROR: context['df'] is None — no DataFrame passed")
        return {"success": False, "result": [], "error": "context['df'] is None"}

    if df.empty:
        print("[release_pend_run_batch] WARNING: DataFrame is empty — nothing to process")
        return {"success": True, "result": []}

    print(f"[release_pend_run_batch] {len(df)} rows to process. Columns: {list(df.columns)}")

    _df_cols_upper = [c.upper() for c in df.columns]
    for _col in ("CLAIM_NO", "DRAFTS", "CLAIM_TYPE", "RULE"):
        if _col not in _df_cols_upper:
            print(f"[release_pend_run_batch] WARNING: Expected column '{_col}' not found — check your DataFrame")

    if dx_code_ref_path:
        if not os.path.exists(dx_code_ref_path):
            print(f"[release_pend_run_batch] ERROR: dx_code_ref_path does not exist: {dx_code_ref_path!r}")
            return {"success": False, "result": [], "error": f"dx_code_ref_path not found: {dx_code_ref_path}"}
        print(f"[release_pend_run_batch] Code ref path OK: {dx_code_ref_path!r}")
    else:
        print("[release_pend_run_batch] WARNING: dx_code_ref_path is empty — code refs will be empty dicts")

    # ── Load DX code references ───────────────────────────────────────────
    print(f"[release_pend_run_batch] Loading code refs from: {dx_code_ref_path!r}")
    try:
        codes = load_code_refs(dx_code_ref_path) if dx_code_ref_path else {}
        for _k, _v in codes.items():
            print(f"  code ref '{_k}': {len(_v)} entries")
    except Exception as _e:
        print(f"[release_pend_run_batch] ERROR loading code refs: {_e}")
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"load_code_refs failed: {_e}"}

    # ── Load rule code reference ──────────────────────────────────────────
    print(f"[release_pend_run_batch] Loading rule code ref from: {rule_code_ref_path!r}")
    try:
        rule_ref = _load_rule_code_ref(rule_code_ref_path) if rule_code_ref_path else {}
        print(f"[release_pend_run_batch] Loaded {len(rule_ref)} rules: {list(rule_ref.keys())}")
    except Exception as _e:
        print(f"[release_pend_run_batch] ERROR loading rule code ref: {_e}")
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"_load_rule_code_ref failed: {_e}"}

    # ── Connect to emulator ───────────────────────────────────────────────
    # system.ActiveSession only returns a session when an EXTRA window has
    # Windows UI focus, which isn't reliable off the main thread — use the
    # same robust multi-session attach as claims.py/OI_YES_NO. We still only
    # process on ONE session (sequentially, in original row order): later
    # rows can be auto-skipped via cert_no_skip when an earlier row for the
    # same CERT_NO failed/pended, and that only holds if same-cert rows run
    # in order on a single session — splitting rows across sessions would
    # silently break that logic.
    print("[release_pend_run_batch] Connecting to EXTRA.System...")
    try:
        sessions = attach_emulator_sessions(n=4)
        sess = sessions[0]
        screen = sess.Screen
        print(f"[release_pend_run_batch] Emulator connected. Initial screen: {get_screen_id(screen)!r}")
    except Exception as _e:
        print(f"[release_pend_run_batch] ERROR connecting to emulator: {_e}")
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"Emulator connection failed: {_e}"}

    results = []
    cert_no_skip = ""

    for _row_idx, (_, row_series) in enumerate(df.iterrows(), start=1):
        row = {k: (str(v).strip() if v is not None else "") for k, v in row_series.to_dict().items()}
        claim_no = row.get("CLAIM_NO", "")

        try:
            total_drafts = int(row.get("DRAFTS", 1) or 1)
        except (ValueError, TypeError):
            total_drafts = 1
            print(f"[{claim_no}] WARNING: DRAFTS value {row.get('DRAFTS')!r} is not a number — defaulting to 1")

        print(f"\n[{claim_no}] ── Row {_row_idx}/{len(df)} ──────────────────────────────────────────────────────")
        print(f"[{claim_no}]  DRAFTS={total_drafts}  CLAIM_TYPE={row.get('CLAIM_TYPE','')!r}  CERT_NO={row.get('CERT_NO','')!r}")

        if not claim_no:
            print(f"[{claim_no}] WARNING: CLAIM_NO is empty on row {_row_idx} — skipping")
            results.append({"CLAIM CONTROL #": "", "MACRO STATUS": "SKIPPED: empty CLAIM_NO"})
            continue

        _stage = "init"
        try:

            # ── Resolve settings from rule CSV ────────────────────────────
            # Case-insensitive column lookup so 'rule', 'RULE', 'Rule' all work
            rule_val = next((v for k, v in row.items() if k.upper() == "RULE"), "")
            rule_key = rule_val.strip().upper()
            if not rule_key:
                print(f"[{claim_no}] SKIPPED: RULE column is empty")
                results.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": "SKIPPED: RULE column is empty"})
                continue
            if rule_key not in rule_ref:
                print(f"[{claim_no}] SKIPPED: RULE {rule_key!r} not found in rule CSV")
                results.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": f"SKIPPED: RULE {rule_key!r} not found in rule CSV"})
                continue
            row_settings = rule_ref[rule_key].copy()
            row["RULE_KEY"] = rule_key
            print(f"[{claim_no}] Loaded settings from rule {rule_key!r}")

            # ── Seed AP/PRV codes from rule CSV into the claim row ────────
            if row_settings.get("new_ap_cd", "") and not row.get("NEW_AP_CD", ""):
                row["NEW_AP_CD"] = row_settings["new_ap_cd"]
                print(f"[{claim_no}] NEW_AP_CD set from rule CSV: {row['NEW_AP_CD']!r}")
            if row_settings.get("new_prv_cd", "") and not row.get("NEW_PRV_CD", ""):
                row["NEW_PRV_CD"] = row_settings["new_prv_cd"]
                print(f"[{claim_no}] NEW_PRV_CD set from rule CSV: {row['NEW_PRV_CD']!r}")

            # ── Final decision summary ────────────────────────────────────
            _deny = row_settings.get("deny_clm", "N") == "Y"
            _dc   = row_settings.get("denial_code", "").strip()
            _prv  = row.get("NEW_PRV_CD", "").strip()
            _eob  = row.get("EOB_PER_CLM", "").strip()
            if _deny:
                _decision = f"DENY  | code={_dc or '(from settings)'}"
            else:
                _decision = "RELEASE (no denial)"
            _extras = []
            if _prv:
                _extras.append(f"PRV={_prv}")
            if _eob:
                _extras.append(f"EOB='{_eob[:50]}{'...' if len(_eob) > 50 else ''}'")
            if _extras:
                _decision += "  |  " + "  ".join(_extras)
            print(f"[{claim_no}] >>> DECISION: {_decision}")

            # ── Seq-order skip ────────────────────────────────────────────
            if row_settings.get("seq_ordr", "N") == "Y":
                if cert_no_skip and cert_no_skip == row.get("CERT_NO", ""):
                    print(f"[{claim_no}] SKIPPED (SEQ ORDER) — cert_no_skip={cert_no_skip!r} matches")
                    results.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": "SKIPPED (SEQ ORDER)"})
                    send_pf(screen, 9)
                    continue

            # ── TOD update ────────────────────────────────────────────────
            if row_settings.get("aply_tod_updt", "N") == "Y":
                _stage = "tod_update"
                _tod_val = row.get("TOD", "")
                print(f"[{claim_no}] Running TOD update (TOD={_tod_val!r})...")
                if not tod_update(screen, row, row_settings):
                    _msg = row.get("MACRO_STATUS", "TOD UPDATE FAILED")
                    print(f"[{claim_no}] TOD update FAILED: {_msg!r}")
                    results.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": _msg})
                    send_pf(screen, 9)
                    continue
                print(f"[{claim_no}] TOD update OK")

            # ── Navigate to CPS520.01 ─────────────────────────────────────
            _stage = "navigate_cps520"
            print(f"[{claim_no}] Navigating to CPS520.01... (current: {get_screen_id(screen)!r})")
            for _attempt in range(15):
                send_pf(screen, 9)
                _cur = get_screen_id(screen)
                if _cur == "CPS520.01":
                    print(f"[{claim_no}]   On CPS520.01 after {_attempt + 1} PF9(s). Placing claim number.")
                    place_value(screen, claim_no, 8, 15)
                    remove_value(screen, 9, 15)
                    remove_value(screen, 12, 15)
                    break
                print(f"[{claim_no}]   nav attempt {_attempt + 1}: screen={_cur!r} — placing claim on current screen, retrying")
                send_pf(screen, 9)
                place_value(screen, claim_no, 8, 15)
                remove_value(screen, 9, 15)
                remove_value(screen, 12, 15)
            else:
                print(f"[{claim_no}]   WARNING: Never reached CPS520.01 after 15 attempts. Last screen: {get_screen_id(screen)!r}")

            _stage = "claim_enter"
            send_enter(screen)
            _scr = get_screen_id(screen)
            print(f"[{claim_no}] After claim entry: screen={_scr!r}")

            if _scr == "CPS520.01":
                _err = (screen.GetString(31, 2, 70) or "").strip()
                print(f"[{claim_no}] ERROR: Still on CPS520 after enter — {_err!r}")
                results.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": _err})
                send_pf(screen, 9)
                continue

            # ── Draft loop ────────────────────────────────────────────────
            j = 1
            row_done = True
            final_status = ""

            for i in range(1, total_drafts + 1):
                print(f"[{claim_no}] ── Draft {i}/{total_drafts} (selector j={j}) ──")

                # Navigate back to claim list
                _stage = f"draft_{i}_navigate"
                for _attempt in range(10):
                    send_pf(screen, 9)
                    _cur = get_screen_id(screen)
                    if _cur == "CPS520.01":
                        place_value(screen, claim_no, 8, 15)
                        remove_value(screen, 9, 15)
                        remove_value(screen, 12, 15)
                        break
                    print(f"[{claim_no}]   draft {i} nav attempt {_attempt + 1}: screen={_cur!r}")
                    send_pf(screen, 9)
                    place_value(screen, claim_no, 8, 15)
                    remove_value(screen, 9, 15)
                    remove_value(screen, 12, 15)

                send_enter(screen)
                print(f"[{claim_no}] Draft {i}: after claim enter, screen={get_screen_id(screen)!r}")

                # Select draft line
                _stage = f"draft_{i}_select"
                if row_settings.get("lst_rls", "Y") != "Y":
                    if i == 8:
                        j = 1
                        send_pf(screen, 11)
                    elif i > 8:
                        send_pf(screen, 11)
                    print(f"[{claim_no}] Draft {i}: placing selector {j:02d} (non-lst_rls mode)")
                    place_value(screen, f"{j:02d}", 3, 26)
                else:
                    _found_dr = None
                    for dr in range(6, 19, 2):
                        _dr_status = (screen.GetString(dr, 6, 2) or "").strip()
                        if _dr_status != "66":
                            _found_dr = (screen.GetString(dr, 2, 2) or "").strip()
                            place_value(screen, _found_dr, 3, 26)
                            break
                    print(f"[{claim_no}] Draft {i}: lst_rls mode — selected draft row={_found_dr!r}")
                    if _found_dr is None:
                        print(f"[{claim_no}] Draft {i}: WARNING — no non-66 draft found on this page")

                send_enter(screen)
                _scr_draft = get_screen_id(screen)
                print(f"[{claim_no}] Draft {i}: after draft select, screen={_scr_draft!r}")

                # ── CPS850 ────────────────────────────────────────────────
                _stage = f"draft_{i}_cps850"
                if _scr_draft == "CPS850.01":
                    coded_opi = (screen.GetString(15, 59, 4) or "").strip()
                    row["CODED_OPI"] = coded_opi
                    print(f"[{claim_no}] Draft {i}: On CPS850 — coded_OPI={coded_opi!r}")

                    _opi_mode = row_settings.get("aply_opi", "N")
                    if _opi_mode in ("Y", "D"):
                        print(f"[{claim_no}] Draft {i}: Applying OPI mode={_opi_mode!r}, NEW_OPI={row.get('NEW_OPI','')!r}")
                        if _opi_mode == "Y":
                            place_value(screen, row.get("NEW_OPI", ""), 22, 58)
                        else:
                            remove_value(screen, 22, 58)
                        place_value(screen, "x", 23, 52)
                        send_enter(screen)
                        if get_screen_id(screen) == "CPS850.01":
                            final_status = (screen.GetString(31, 2, 60) or "").strip()
                            print(f"[{claim_no}] Draft {i}: OPI FAILED — still on 850: {final_status!r}")
                            row_done = False
                            break
                        send_pf(screen, 8)
                        place_value(screen, "850", 2, 37)
                        send_enter(screen)
                        row["CODED_OPI"] = (screen.GetString(15, 59, 4) or "").strip()
                        print(f"[{claim_no}] Draft {i}: OPI applied, refreshed OPI={row['CODED_OPI']!r}")

                    _850_nt = row_settings.get("aply_850_nt", "DO NOT APPLY NOTE")
                    if _850_nt in ("APPEND ON CURRENT NOTE", "2ND LINE ONLY"):
                        print(f"[{claim_no}] Draft {i}: Placing CSR note ({_850_nt!r})")
                        place_new_csr_note(screen, row, _850_nt)

                    if row_settings.get("chnge_dx_cd", "N") == "Y":
                        print(f"[{claim_no}] Draft {i}: Changing DX code → {row.get('DX_CD','')!r}")
                        place_value(screen, row.get("DX_CD", ""), 23, 6)
                        place_value(screen, "Y", 23, 14)

                    if row_settings.get("aply_int_zip", "N") == "Y":
                        print(f"[{claim_no}] Draft {i}: Applying INT/ZIP (ZIP={row.get('ZIP','')!r}, INT_NO={row.get('INT_NO','')!r})")
                        place_value(screen, "X", 29, 26)
                        send_enter(screen)
                        if get_screen_id(screen) == "CPS325.01":
                            place_value(screen, row.get("ZIP", ""), 5, 69)
                            place_value(screen, row.get("INT_NO", ""), 7, 30)
                            send_enter(screen)
                        else:
                            print(f"[{claim_no}] Draft {i}: WARNING — expected CPS325.01 for INT/ZIP but got {get_screen_id(screen)!r}")
                else:
                    print(f"[{claim_no}] Draft {i}: NOT on CPS850 ({_scr_draft!r}) — skipping 850 block")

                _stage = f"draft_{i}_post850_enter"
                send_enter(screen)
                _scr_post850 = get_screen_id(screen)
                print(f"[{claim_no}] Draft {i}: after 850 enter → screen={_scr_post850!r}")

                # ── CPS910 TOD prompt ─────────────────────────────────────
                _stage = f"draft_{i}_cps910"
                if _scr_post850 == "CPS910.01":
                    _tod_val = str(row.get("TOD", "")).zfill(2)
                    print(f"[{claim_no}] Draft {i}: CPS910 TOD prompt — entering TOD={_tod_val!r}")
                    place_value(screen, _tod_val, 5, 60)
                    send_enter(screen)
                    if get_screen_id(screen) == "CPS910.01":
                        final_status = (screen.GetString(31, 2, 70) or "").strip()
                        print(f"[{claim_no}] Draft {i}: CPS910 TOD FAILED: {final_status!r}")
                        row_done = False
                        break
                    print(f"[{claim_no}] Draft {i}: CPS910 TOD OK → {get_screen_id(screen)!r}")

                # ── Condition note ────────────────────────────────────────
                _stage = f"draft_{i}_cond_note"
                if row_settings.get("aply_cond_nt", "N") == "Y":
                    print(f"[{claim_no}] Draft {i}: Adding condition note (COND_NOTE={row.get('COND_NOTE','')!r})...")
                    if not add_condition_note(screen, row):
                        final_status = row.get("MACRO_STATUS", "ERROR ADDING CONDITION NOTE")
                        print(f"[{claim_no}] Draft {i}: Condition note FAILED: {final_status!r}")
                        row_done = False
                        break
                    print(f"[{claim_no}] Draft {i}: Condition note OK")

                # ── Condition AFV ─────────────────────────────────────────
                _stage = f"draft_{i}_cond_afv"
                if row_settings.get("aply_cond_afv", "N") == "Y":
                    print(f"[{claim_no}] Draft {i}: Updating condition AFV (AFV={row.get('AFV','')!r})...")
                    if not update_condition_afv(screen, row):
                        final_status = row.get("MACRO_STATUS", "ERROR UPDATING CONDITION AFV")
                        print(f"[{claim_no}] Draft {i}: Condition AFV FAILED: {final_status!r}")
                        row_done = False
                        break
                    print(f"[{claim_no}] Draft {i}: Condition AFV OK")

                claim_type = row.get("CLAIM_TYPE", "").upper().strip()
                print(f"[{claim_no}] Draft {i}: CLAIM_TYPE={claim_type!r}, screen={get_screen_id(screen)!r}")

                if not claim_type:
                    print(f"[{claim_no}] Draft {i}: ERROR — CLAIM_TYPE is empty. Check your DataFrame.")

                # ── UB branch ─────────────────────────────────────────────
                _stage = f"draft_{i}_data_entry_{claim_type or 'UNKNOWN'}"
                if claim_type == "UB":
                    if row_settings.get("updt_frm_to_dt", "N") == "Y":
                        _from = (screen.GetString(2, 63, 6) or "").strip()
                        _thru = (screen.GetString(2, 75, 6) or "").strip()
                        _svc  = (screen.GetString(6, 17, 6) or "").strip()
                        print(f"[{claim_no}] Draft {i}: Sync dates — FROM={_from!r} THRU={_thru!r} SERV={_svc!r}")
                        if _from != _svc:
                            remove_value(screen, 2, 63)
                            place_value(screen, _svc, 2, 63)
                        if _thru != _svc:
                            remove_value(screen, 2, 75)
                            place_value(screen, _svc, 2, 75)

                    print(f"[{claim_no}] Draft {i}: apply_ineligibility_codes(UB)...")
                    apply_ineligibility_codes(screen, "UB", row, row_settings, codes.get("dny_by_cpt", {}))

                    if row_settings.get("chk_per_diem", "N") == "Y":
                        print(f"[{claim_no}] Draft {i}: Running ub_per_diem_process...")
                        ub_per_diem_process(screen, row, row_settings)
                        cert_no_skip = row.get("CERT_NO", "")
                        row_done = False
                        final_status = row.get("MACRO_STATUS", "PER DIEM PROCESSED")
                        print(f"[{claim_no}] Draft {i}: Per-diem done: {final_status!r}")
                        break

                    status_parts: list = []
                    print(f"[{claim_no}] Draft {i}: Running ub_data_entry...")
                    res = ub_data_entry(screen, row, row_settings, codes, status_parts)
                    print(f"[{claim_no}] Draft {i}: ub_data_entry → res={res}, parts={status_parts}")
                    if res == 0:
                        cert_no_skip = row.get("CERT_NO", "")
                        final_status = "; ".join(status_parts) if status_parts else row.get("MACRO_STATUS", "UB ENTRY FAILED")
                        row_done = False
                        break
                    cert_no_skip = ""

                # ── HCFA branch ───────────────────────────────────────────
                elif claim_type == "HCFA":
                    print(f"[{claim_no}] Draft {i}: apply_ineligibility_codes(HCFA)...")
                    apply_ineligibility_codes(screen, "HCFA", row, row_settings, codes.get("dny_by_cpt", {}))

                    status_parts = []
                    print(f"[{claim_no}] Draft {i}: Running hcfa_data_entry...")
                    res = hcfa_data_entry(screen, row, row_settings, codes, status_parts)
                    print(f"[{claim_no}] Draft {i}: hcfa_data_entry → res={res}, parts={status_parts}")
                    if res == 0:
                        cert_no_skip = row.get("CERT_NO", "")
                        final_status = "; ".join(status_parts) if status_parts else row.get("MACRO_STATUS", "HCFA ENTRY FAILED")
                        row_done = False
                        break
                    cert_no_skip = ""

                else:
                    print(f"[{claim_no}] Draft {i}: INVALID CLAIM_TYPE={claim_type!r} — must be 'UB' or 'HCFA'")
                    final_status = "INVALID CLAIM TYPE."
                    row_done = False
                    break

                j += 1
                print(f"[{claim_no}] Draft {i}: completed OK")

            macro_status = "DONE." if row_done else final_status
            print(f"[{claim_no}] ── RESULT: {macro_status!r}")
            results.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": macro_status})

        except Exception as exc:
            print(f"[{claim_no}] EXCEPTION at stage={_stage!r}: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            results.append({
                "CLAIM CONTROL #": claim_no,
                "MACRO STATUS": f"EXCEPTION [{_stage}]: {type(exc).__name__}: {exc}",
            })
        finally:
            try:
                send_pf(screen, 9)
            except Exception as _fe:
                print(f"[{claim_no}] WARNING: PF9 in finally block failed: {_fe}")

    print(f"\n[release_pend_run_batch] Done. Processed {len(results)}/{len(df)} claims.")
    return {"success": True, "result": results}


# ---------------------------------------------------------------------------
# Claim-details fetch (mirrors Get_Claim_Details + GridPriceCheck VBA)
# ---------------------------------------------------------------------------
def _process_claim_detail_row(screen, row, claim_no, aply_grid_prc, grid_price):
    """
    Per-row body of release_pend_get_claim_details. Each row is independent
    (no cross-row state like release_pend_run_batch's cert_no_skip), so this
    is safe to run on any session/thread.
    """
    try:
        # Navigate to CPS520.01 and enter claim number
        for _ in range(15):
            if get_screen_id(screen) == "CPS520.01":
                place_value(screen, claim_no, 8, 15)
                remove_value(screen, 9, 15)
                remove_value(screen, 12, 15)
                break
            send_pf(screen, 9)
        else:
            send_pf(screen, 9)
            place_value(screen, claim_no, 8, 15)
            remove_value(screen, 9, 15)
            remove_value(screen, 12, 15)

        send_enter(screen)

        if get_screen_id(screen) == "CPS520.01":
            row["MACRO_STATUS"] = (screen.GetString(31, 2, 70) or "").strip()
            send_pf(screen, 9)
            return row

        # Read pending code
        row["PEND_CD"] = (screen.GetString(6, 6, 3) or "").strip()

        # Count drafts (may span multiple pages)
        t_draft = 0
        while True:
            for line in range(6, 19, 2):
                if (screen.GetString(line, 2, 3) or "").strip():
                    t_draft += 1
            if "MORE DATA" in (screen.GetString(20, 2, 60) or "").upper():
                send_pf(screen, 11)
            else:
                break

        row["DRAFTS"] = str(t_draft)

        # GridPriceCheck: navigate drafts to find claim type and grid mismatches
        send_pf(screen, 9)
        place_value(screen, claim_no, 8, 15)
        remove_value(screen, 9, 15)
        remove_value(screen, 12, 15)
        send_enter(screen)

        t_pages = max(1, (t_draft + 6) // 7)
        dctr = 1
        claim_type = ""
        status_parts: list = []

        for pg in range(1, t_pages + 1):
            for d_line in range(1, 8):
                place_value(screen, f"{d_line:02d}", 3, 26)
                send_enter(screen)
                row["REL"] = (screen.GetString(13, 27, 2) or "").strip()
                send_enter(screen)

                sid = get_screen_id(screen)
                if sid == "CPS450.01":
                    claim_type = "HCFA"
                    row["OLD_POS"] = (screen.GetString(2, 6, 3) or "").strip()
                    if aply_grid_prc == "Y":
                        for c2 in range(5, 12, 2):
                            if not (screen.GetString(c2, 4, 6) or "").strip():
                                break
                            try:
                                chg  = float((screen.GetString(c2, 26, 7) or "0").strip())
                                proc = (screen.GetString(c2, 41, 6) or "").strip()
                                allowed = grid_price.get(proc, 0)
                                if allowed and chg != allowed:
                                    msg = f"PRICE MISMATCH {proc}(Pg:{pg} Ln:{d_line:02d})"
                                    status_parts.append(msg)
                            except (ValueError, TypeError):
                                pass
                    else:
                        break

                elif sid == "BLX2460.01":
                    claim_type = "UB"
                    row["OLD_POS"] = (screen.GetString(1, 26, 3) or "").strip()
                    break

                dctr += 1
                if dctr > t_draft:
                    break

                send_pf(screen, 9)
                place_value(screen, claim_no, 8, 15)
                remove_value(screen, 9, 15)
                remove_value(screen, 12, 15)
                send_enter(screen)

            if claim_type in ("HCFA", "UB") and aply_grid_prc != "Y":
                break
            send_pf(screen, 11)

        row["CLAIM_TYPE"]   = claim_type
        row["MACRO_STATUS"] = "; ".join(status_parts) if status_parts else ""

        # Read old provider code from CPS408 screen
        send_pf(screen, 8)
        place_value(screen, "408", 2, 37)
        send_enter(screen)
        row["OLD_PRV_CD"] = "'" + (screen.GetString(3, 48, 1) or "").strip()
        send_pf(screen, 9)

        return row

    except Exception as exc:
        row["MACRO_STATUS"] = f"EXCEPTION: {type(exc).__name__}: {exc}"
        send_pf(screen, 9)
        return row


@register_function(
    name="release_pend_get_claim_details",
    tag="Release Pend Macro",
    color="#2e7d32",
    inputs=[
        {"name": "dx_code_ref_path", "type": "str",                        "default": ""},
        {"name": "aply_grid_prc",    "type": "str", "options": ["Y", "N"], "default": "N"},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "result",  "type": "list"},
    ],
)
def release_pend_get_claim_details(
    dx_code_ref_path: str,
    aply_grid_prc: str = "N",
    context=None,
):
    """
    Mirrors Get_Claim_Details + GridPriceCheck VBA.
    For each row in context['df'] reads: pending code, draft count, claim type, grid price mismatches.
    Writes results back as a list of dicts with updated row data.
    Rows are independent, so they're processed in parallel across up to 4
    emulator sessions (round-robin), same pattern as claims.py/OI_YES_NO.
    """
    df = context.get("df")

    codes = load_code_refs(dx_code_ref_path)
    grid_price = codes.get("grid_price", {})

    try:
        sessions = attach_emulator_sessions(n=4)
    except Exception as e:
        print(f"[release_pend_get_claim_details] Failed to attach sessions: {e}")
        raise

    worker_count = min(4, len(sessions))
    print(f"[release_pend_get_claim_details] Using {worker_count} emulator session(s) for {len(df)} row(s).")

    # (position, (df_index, row_series)) so results can be reassembled in original order
    indexed_rows = list(enumerate(df.iterrows()))
    buckets = [indexed_rows[i::worker_count] for i in range(worker_count)]

    out_q: Queue = Queue()

    def _worker(worker_idx, items):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            session = sessions[worker_idx]
            screen = session.Screen
            try:
                screen.WaitHostQuiet(2000)
            except Exception:
                pass

            for pos, (_, row_series) in items:
                row = {k: (str(v).strip() if v is not None else "") for k, v in row_series.to_dict().items()}
                claim_no = row.get("CLAIM_NO", "")
                try:
                    res = _process_claim_detail_row(screen, row, claim_no, aply_grid_prc, grid_price)
                except Exception as exc:
                    print(f"[release_pend_get_claim_details] Worker {worker_idx} error on {claim_no}: {exc}")
                    row["MACRO_STATUS"] = f"EXCEPTION: {type(exc).__name__}: {exc}"
                    res = row
                out_q.put((pos, res))
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for i in range(worker_count):
            pool.submit(_worker, i, buckets[i])

        results = [None] * len(indexed_rows)
        collected = 0
        while collected < len(indexed_rows):
            pos, res = out_q.get()
            results[pos] = res
            collected += 1

    return {"success": True, "result": results}
