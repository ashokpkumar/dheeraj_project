"""
Release / Pend Macro — main registered functions.
Ports Release_or_Pend_Claim and Get_Claim_Details from Modules_oShared.txt.
"""

import csv
import os
import traceback
import win32com.client

from rule_engine.registry import register_function

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
# Helper: build settings dict from individual function parameters
# ---------------------------------------------------------------------------
def _build_settings(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items()}


# ---------------------------------------------------------------------------
# Helper: load denial_code_ref.csv
# ---------------------------------------------------------------------------
def _load_denial_code_ref(path: str) -> dict:
    """
    Reads denial_code_ref.csv and returns a dict keyed by uppercase rule name.
    Each value has: denial_code, prv_code, eob_comment, extra_comment.
    """
    ref = {}
    if not path or not os.path.exists(path):
        return ref
    with open(path, newline="", encoding="utf-8") as _f:
        for _row in csv.DictReader(_f):
            rule = (_row.get("Rule") or "").strip().upper()
            if rule:
                ref[rule] = {
                    "denial_code":   (_row.get("Denial code")   or "").strip(),
                    "prv_code":      (_row.get("PRV code")       or "").strip(),
                    "eob_comment":   (_row.get("EOB comment")    or "").strip(),
                    "extra_comment": (_row.get("Extra comment")  or "").strip(),
                }
    return ref


# ---------------------------------------------------------------------------
# Main batch function
# ---------------------------------------------------------------------------
@register_function(
    name="release_pend_run_batch",
    tag="Release Pend Macro",
    color="#2e7d32",
    inputs=[
        # --- source file ---
        {"name": "dx_code_ref_path",      "type": "str", "default": ""},
        {"name": "denial_code_ref_path",  "type": "str", "default": ""},
        # --- CPS506 release screen ---
        {"name": "rls_code",   "type": "str",                              "default": "10"},
        {"name": "lst_rls",    "type": "str", "options": ["Y", "N"],       "default": "Y"},
        {"name": "pnd_rsn",    "type": "str",                              "default": ""},
        {"name": "pnd_op_id",  "type": "str",                              "default": ""},
        {"name": "flw_up",     "type": "str",                              "default": ""},
        {"name": "dist_unit",  "type": "str",                              "default": ""},
        {"name": "eob",        "type": "str",                              "default": ""},
        {"name": "ck",         "type": "str",                              "default": ""},
        {"name": "note",       "type": "str",                              "default": ""},
        {"name": "payee",      "type": "str", "options": ["0", "1", "2", "3"], "default": "0"},
        {"name": "eob_note",   "type": "str",                              "default": ""},
        {"name": "verify",     "type": "str", "options": ["Y", "N"],       "default": "N"},
        # --- OI / UC ---
        {"name": "apply_uc",        "type": "str", "options": ["Y", "N"],                        "default": "Y"},
        {"name": "rem_oi_elig_amt", "type": "str", "options": ["Y", "N"],                        "default": "N"},
        {"name": "apply_001",       "type": "str", "options": ["N/A", "1 ONLY", "ALL LINES"],    "default": "N/A"},
        {"name": "deny_clm",        "type": "str", "options": ["Y", "N"],                        "default": "N"},
        {"name": "add_time",        "type": "str", "options": ["Y", "N"],                        "default": "N"},
        # --- inel amt/cd ---
        {"name": "vld_amt_pd",             "type": "str", "options": ["Y", "N"],                                              "default": "N"},
        {"name": "vld_amt_pd_by_cpt",      "type": "str", "options": ["Y", "N"],                                              "default": "N"},
        {"name": "remove_prv",             "type": "str", "options": ["Y", "N"],                                              "default": "N"},
        {"name": "remove_inel_amt_cd",     "type": "str", "options": ["N/A", "INEL/CD1", "INEL/CD2", "INEL/CD ALL", "SPECIFIC"], "default": "N/A"},
        {"name": "denial_code",            "type": "str",                                                                     "default": ""},
        {"name": "aply_inel_cd_spcfc_rmval","type": "str", "options": ["Y", "N"],                                             "default": "N"},
        {"name": "inel_cd_to_rmv",         "type": "str",                                                                     "default": ""},
        # --- DX / Lab / Rev ---
        {"name": "apply_dx",        "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "apply_lab",       "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "dx_lab_rev",      "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "apply_bn_t_hold", "type": "str", "options": ["Y", "N"], "default": "N"},
        # --- BN / Modifier ---
        {"name": "apply_bn_qty",   "type": "str", "options": ["Y", "N"],            "default": "N"},
        {"name": "chnge_dx_cd",    "type": "str", "options": ["Y", "N"],            "default": "N"},
        {"name": "new_oi_elig_pd", "type": "str", "options": ["N/A", "Y", "N"],     "default": "N/A"},
        {"name": "new_oi_indctr",  "type": "str", "options": ["N/A", "Y", "N"],     "default": "N/A"},
        {"name": "inel_switch",    "type": "str", "options": ["Y", "N"],            "default": "N"},
        # --- DX exception / Condition / Grid ---
        {"name": "aply_dx_excptn", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "aply_cond_nt",   "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "aply_grid_prc",  "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "updt_frm_to_dt", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "aply_tod_updt",  "type": "str", "options": ["Y", "N"], "default": "N"},
        # --- AP code / Int-Zip / Cond-AFV ---
        {"name": "remove_ap",    "type": "str", "options": ["Y", "N"],                                                    "default": "N"},
        {"name": "aply_int_zip", "type": "str", "options": ["Y", "N"],                                                    "default": "N"},
        {"name": "aply_cond_afv","type": "str", "options": ["Y", "N"],                                                    "default": "N"},
        {"name": "aply_850_nt",  "type": "str", "options": ["DO NOT APPLY NOTE", "APPEND ON CURRENT NOTE", "2ND LINE ONLY"], "default": "DO NOT APPLY NOTE"},
        {"name": "rem_code_set", "type": "str", "options": ["Y", "N"],                                                    "default": "N"},
        # --- Modifier / Provider ---
        {"name": "aply_modifr",    "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "inel_code",      "type": "str",                        "default": ""},
        {"name": "remv_prov_rate", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "remv_modifr",    "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "aply_two_ap_cd", "type": "str", "options": ["Y", "N"], "default": "N"},
        # --- Bypass / 858 / Bond / HIC ---
        {"name": "remv_prcrt_byps","type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "amt_858_inq",    "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "bond_clinic",    "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "updt_oc_for_700","type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "updt_hic",       "type": "str", "options": ["Y", "N"], "default": "N"},
        # --- Adj / 631 / State-Type ---
        {"name": "remv_adj_cd",  "type": "str", "options": ["Y", "N"],            "default": "N"},
        {"name": "aply_631_inel","type": "str", "options": ["Y", "N"],            "default": "N"},
        {"name": "aply_st_typ",  "type": "str", "options": ["N/A", "Y", "N"],     "default": "N/A"},
        {"name": "aply_dpsv",    "type": "str", "options": ["Y", "N"],            "default": "Y"},
        {"name": "chk_inel",     "type": "str", "options": ["Y", "N"],            "default": "N"},
        # --- Per-diem / Discount-after-denial ---
        {"name": "chk_per_diem",  "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "dis_aft_dnl",   "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "seq_ordr",      "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "rem_iu",        "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "rem_tu",        "type": "str", "options": ["Y", "N"], "default": "N"},
        # --- OPI / BN delete / Medicare denial ---
        {"name": "aply_opi",           "type": "str", "options": ["N", "Y", "D"], "default": "N"},
        {"name": "del_bn",             "type": "str", "options": ["Y", "N"],      "default": "N"},
        {"name": "aply_dnl_aft_medcr", "type": "str", "options": ["Y", "N"],     "default": "N"},
        # --- Flip-mod / Disc-after-flip ---
        {"name": "flip_mod",            "type": "str", "options": ["Y", "N"],                    "default": "N"},
        {"name": "apply_disc_aft_flip", "type": "str", "options": ["Y", "N"],                    "default": "N"},
        {"name": "rem_disc_amt_flag",   "type": "str", "options": ["N", "Y", "Y-DONT READ OITYPE"], "default": "N"},
        # --- FAIE / 034 / S9451 / HCR ---
        {"name": "faie_adj_inel", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "aply_034_inel", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "dny_s9451",     "type": "str", "options": ["Y", "N"], "default": "Y"},
        {"name": "id_hcr",        "type": "str", "options": ["Y", "N"], "default": "Y"},
        {"name": "2nd_inel_001",  "type": "str", "options": ["Y", "N"], "default": "N"},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "result",  "type": "list"},
    ],
)
def release_pend_run_batch(
    dx_code_ref_path: str,
    denial_code_ref_path: str = "",
    # CPS506 fields
    rls_code:   str = "10",
    lst_rls:    str = "Y",
    pnd_rsn:    str = "",
    pnd_op_id:  str = "",
    flw_up:     str = "",
    dist_unit:  str = "",
    eob:        str = "",
    ck:         str = "",
    note:       str = "",
    payee:      str = "0",
    eob_note:   str = "",
    verify:     str = "N",
    # OI / UC
    apply_uc:        str = "Y",
    rem_oi_elig_amt: str = "N",
    apply_001:       str = "N/A",
    deny_clm:        str = "N",
    add_time:        str = "N",
    # inel amt/cd
    vld_amt_pd:              str = "N",
    vld_amt_pd_by_cpt:       str = "N",
    remove_prv:              str = "N",
    remove_inel_amt_cd:      str = "N/A",
    denial_code:             str = "",
    aply_inel_cd_spcfc_rmval:str = "N",
    inel_cd_to_rmv:          str = "",
    # DX / Lab / Rev
    apply_dx:        str = "N",
    apply_lab:       str = "N",
    dx_lab_rev:      str = "N",
    apply_bn_t_hold: str = "N",
    # BN / Modifier
    apply_bn_qty:  str = "N",
    chnge_dx_cd:   str = "N",
    new_oi_elig_pd:str = "N/A",
    new_oi_indctr: str = "N/A",
    inel_switch:   str = "N",
    # DX exception / Condition / Grid
    aply_dx_excptn:str = "N",
    aply_cond_nt:  str = "N",
    aply_grid_prc: str = "N",
    updt_frm_to_dt:str = "N",
    aply_tod_updt: str = "N",
    # AP code / Int-Zip / Cond-AFV
    remove_ap:     str = "N",
    aply_int_zip:  str = "N",
    aply_cond_afv: str = "N",
    aply_850_nt:   str = "DO NOT APPLY NOTE",
    rem_code_set:  str = "N",
    # Modifier / Provider
    aply_modifr:    str = "N",
    inel_code:      str = "",
    remv_prov_rate: str = "N",
    remv_modifr:    str = "N",
    aply_two_ap_cd: str = "N",
    # Bypass / 858 / Bond / HIC
    remv_prcrt_byps:str = "N",
    amt_858_inq:    str = "N",
    bond_clinic:    str = "N",
    updt_oc_for_700:str = "N",
    updt_hic:       str = "N",
    # Adj / 631 / State-Type
    remv_adj_cd:   str = "N",
    aply_631_inel: str = "N",
    aply_st_typ:   str = "N/A",
    aply_dpsv:     str = "Y",
    chk_inel:      str = "N",
    # Per-diem / Discount-after-denial
    chk_per_diem:  str = "N",
    dis_aft_dnl:   str = "N",
    seq_ordr:      str = "N",
    rem_iu:        str = "N",
    rem_tu:        str = "N",
    # OPI / BN delete / Medicare denial
    aply_opi:          str = "N",
    del_bn:            str = "N",
    aply_dnl_aft_medcr:str = "N",
    # Flip-mod / Disc-after-flip
    flip_mod:            str = "N",
    apply_disc_aft_flip: str = "N",
    rem_disc_amt_flag:   str = "N",
    # FAIE / 034 / S9451 / HCR
    faie_adj_inel: str = "N",
    aply_034_inel: str = "N",
    dny_s9451:     str = "Y",
    id_hcr:        str = "Y",
    two_nd_inel_001:str = "N",
    context=None,
):
    """
    Main release/pend batch processor.
    Iterates the DataFrame from context['df'] and processes each claim row
    against the mainframe emulator.
    Returns {"success": True, "result": [{"CLAIM CONTROL #": ..., "MACRO STATUS": ...}]}.
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

    for _col in ("CLAIM_NO", "DRAFTS", "CLAIM_TYPE"):
        if _col not in df.columns:
            print(f"[release_pend_run_batch] WARNING: Expected column '{_col}' not found — check your DataFrame")

    if dx_code_ref_path:
        if not os.path.exists(dx_code_ref_path):
            print(f"[release_pend_run_batch] ERROR: dx_code_ref_path does not exist: {dx_code_ref_path!r}")
            return {"success": False, "result": [], "error": f"dx_code_ref_path not found: {dx_code_ref_path}"}
        print(f"[release_pend_run_batch] Code ref path OK: {dx_code_ref_path!r}")
    else:
        print("[release_pend_run_batch] WARNING: dx_code_ref_path is empty — code refs will be empty dicts")

    settings = {
        "rls_code":   rls_code,
        "lst_rls":    lst_rls,
        "pnd_rsn":    pnd_rsn,
        "pnd_op_id":  pnd_op_id,
        "flw_up":     flw_up,
        "dist_unit":  dist_unit,
        "eob":        eob,
        "ck":         ck,
        "note":       note,
        "payee":      payee,
        "eob_note":   eob_note,
        "verify":     verify,
        "apply_uc":          apply_uc,
        "rem_oi_elig_amt":   rem_oi_elig_amt,
        "apply_001":         apply_001,
        "deny_clm":          deny_clm,
        "add_time":          add_time,
        "vld_amt_pd":              vld_amt_pd,
        "vld_amt_pd_by_cpt":       vld_amt_pd_by_cpt,
        "remove_prv":              remove_prv,
        "remove_inel_amt_cd":      remove_inel_amt_cd,
        "denial_code":             denial_code,
        "aply_inel_cd_spcfc_rmval":aply_inel_cd_spcfc_rmval,
        "inel_cd_to_rmv":          inel_cd_to_rmv,
        "apply_dx":       apply_dx,
        "apply_lab":      apply_lab,
        "dx_lab_rev":     dx_lab_rev,
        "apply_bn_t_hold":apply_bn_t_hold,
        "apply_bn_qty":   apply_bn_qty,
        "chnge_dx_cd":    chnge_dx_cd,
        "new_oi_elig_pd": new_oi_elig_pd,
        "new_oi_indctr":  new_oi_indctr,
        "inel_switch":    inel_switch,
        "aply_dx_excptn": aply_dx_excptn,
        "aply_cond_nt":   aply_cond_nt,
        "aply_grid_prc":  aply_grid_prc,
        "updt_frm_to_dt": updt_frm_to_dt,
        "aply_tod_updt":  aply_tod_updt,
        "remove_ap":      remove_ap,
        "aply_int_zip":   aply_int_zip,
        "aply_cond_afv":  aply_cond_afv,
        "aply_850_nt":    aply_850_nt,
        "rem_code_set":   rem_code_set,
        "aply_modifr":    aply_modifr,
        "inel_code":      inel_code,
        "remv_prov_rate": remv_prov_rate,
        "remv_modifr":    remv_modifr,
        "aply_two_ap_cd": aply_two_ap_cd,
        "remv_prcrt_byps":remv_prcrt_byps,
        "amt_858_inq":    amt_858_inq,
        "bond_clinic":    bond_clinic,
        "updt_oc_for_700":updt_oc_for_700,
        "updt_hic":       updt_hic,
        "remv_adj_cd":    remv_adj_cd,
        "aply_631_inel":  aply_631_inel,
        "aply_st_typ":    aply_st_typ,
        "aply_dpsv":      aply_dpsv,
        "chk_inel":       chk_inel,
        "chk_per_diem":   chk_per_diem,
        "dis_aft_dnl":    dis_aft_dnl,
        "seq_ordr":       seq_ordr,
        "rem_iu":         rem_iu,
        "rem_tu":         rem_tu,
        "aply_opi":           aply_opi,
        "del_bn":             del_bn,
        "aply_dnl_aft_medcr": aply_dnl_aft_medcr,
        "flip_mod":            flip_mod,
        "apply_disc_aft_flip": apply_disc_aft_flip,
        "rem_disc_amt_flag":   rem_disc_amt_flag,
        "faie_adj_inel":  faie_adj_inel,
        "aply_034_inel":  aply_034_inel,
        "dny_s9451":      dny_s9451,
        "id_hcr":         id_hcr,
        "2nd_inel_001":   two_nd_inel_001,
    }

    # ── Load code references ──────────────────────────────────────────────
    print(f"[release_pend_run_batch] Loading code refs from: {dx_code_ref_path!r}")
    try:
        codes = load_code_refs(dx_code_ref_path) if dx_code_ref_path else {}
        for _k, _v in codes.items():
            print(f"  code ref '{_k}': {len(_v)} entries")
    except Exception as _e:
        print(f"[release_pend_run_batch] ERROR loading code refs: {_e}")
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"load_code_refs failed: {_e}"}

    # ── Load denial code reference (active when rls_code=71, lst_rls=Y, deny_clm=Y) ──
    denial_ref_mode = (rls_code == "71" and lst_rls == "Y" and deny_clm == "Y")
    denial_code_ref: dict = {}
    if denial_ref_mode:
        if denial_code_ref_path and os.path.exists(denial_code_ref_path):
            denial_code_ref = _load_denial_code_ref(denial_code_ref_path)
            print(f"[release_pend_run_batch] Loaded {len(denial_code_ref)} denial code ref entries from {denial_code_ref_path!r}")
        else:
            print(f"[release_pend_run_batch] WARNING: denial_ref_mode=True but denial_code_ref_path not provided or not found — "
                  f"column DENIAL_RULE will be ignored")

    # ── Connect to emulator ───────────────────────────────────────────────
    print("[release_pend_run_batch] Connecting to EXTRA.System...")
    try:
        system = win32com.client.Dispatch("EXTRA.System")
        sess   = system.ActiveSession
        if sess is None:
            raise RuntimeError("ActiveSession is None — is the emulator open?")
        screen = sess.Screen
        if screen is None:
            raise RuntimeError("Screen object is None — emulator may not be ready")
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

            # ── Per-claim settings: apply denial_code_ref.csv overrides ──────────
            row_settings = settings.copy()
            if denial_ref_mode and denial_code_ref:
                _rule_key = row.get("DENIAL_RULE", "").strip().upper()
                if _rule_key and _rule_key in denial_code_ref:
                    _ref     = denial_code_ref[_rule_key]
                    _csv_dc  = _ref["denial_code"]
                    _csv_prv = _ref["prv_code"]
                    _csv_eob = _ref["eob_comment"]
                    if _csv_dc == "0":
                        # No denial code needed — release as plain 71Y
                        row_settings["deny_clm"] = "N"
                        print(f"[{claim_no}] DenialRef({_rule_key}): denial disabled — plain 71Y release")
                    elif _csv_dc not in ("#N/A", ""):
                        row_settings["denial_code"] = f"{int(_csv_dc):03d}"
                        print(f"[{claim_no}] DenialRef({_rule_key}): denial_code → {row_settings['denial_code']!r}")
                    if _csv_prv not in ("#N/A", ""):
                        row["NEW_PRV_CD"] = _csv_prv
                        print(f"[{claim_no}] DenialRef({_rule_key}): NEW_PRV_CD → {_csv_prv!r}")
                    if _csv_eob not in ("#N/A", "") and not row.get("EOB_PER_CLM", ""):
                        row["EOB_PER_CLM"] = _csv_eob
                        print(f"[{claim_no}] DenialRef({_rule_key}): EOB_PER_CLM → {_csv_eob!r}")
                elif _rule_key:
                    print(f"[{claim_no}] DenialRef: rule {_rule_key!r} not found in CSV — using default settings")

            # ── Final decision summary ────────────────────────────────────
            _deny      = row_settings.get("deny_clm", "N") == "Y"
            _dc        = row_settings.get("denial_code", "").strip()
            _prv       = row.get("NEW_PRV_CD", "").strip()
            _eob       = row.get("EOB_PER_CLM", "").strip()
            _rls       = row_settings.get("rls_code", "")
            if _deny:
                _decision = f"DENY  | code={_dc or '(from settings)'}"
            else:
                _decision = f"RELEASE 71Y (no denial)"
            _extras = []
            if _prv:
                _extras.append(f"PRV={_prv}")
            if _eob:
                _extras.append(f"EOB='{_eob[:50]}{'...' if len(_eob) > 50 else ''}'")
            if _extras:
                _decision += "  |  " + "  ".join(_extras)
            print(f"[{claim_no}] >>> DECISION: {_decision}")

            # ── Seq-order skip ────────────────────────────────────────────
            if seq_ordr == "Y":
                if cert_no_skip and cert_no_skip == row.get("CERT_NO", ""):
                    print(f"[{claim_no}] SKIPPED (SEQ ORDER) — cert_no_skip={cert_no_skip!r} matches")
                    results.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": "SKIPPED (SEQ ORDER)"})
                    send_pf(screen, 9)
                    continue

            # ── TOD update ────────────────────────────────────────────────
            if aply_tod_updt == "Y":
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

            # ── EntryPoint1: navigate to CPS520.01 ───────────────────────
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
                if lst_rls != "Y":
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

                    if aply_opi in ("Y", "D"):
                        print(f"[{claim_no}] Draft {i}: Applying OPI mode={aply_opi!r}, NEW_OPI={row.get('NEW_OPI','')!r}")
                        if aply_opi == "Y":
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

                    if aply_850_nt in ("APPEND ON CURRENT NOTE", "2ND LINE ONLY"):
                        print(f"[{claim_no}] Draft {i}: Placing CSR note ({aply_850_nt!r})")
                        place_new_csr_note(screen, row, aply_850_nt)

                    if chnge_dx_cd == "Y":
                        print(f"[{claim_no}] Draft {i}: Changing DX code → {row.get('DX_CD','')!r}")
                        place_value(screen, row.get("DX_CD", ""), 23, 6)
                        place_value(screen, "Y", 23, 14)

                    if aply_int_zip == "Y":
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
                if aply_cond_nt == "Y":
                    print(f"[{claim_no}] Draft {i}: Adding condition note (COND_NOTE={row.get('COND_NOTE','')!r})...")
                    if not add_condition_note(screen, row):
                        final_status = row.get("MACRO_STATUS", "ERROR ADDING CONDITION NOTE")
                        print(f"[{claim_no}] Draft {i}: Condition note FAILED: {final_status!r}")
                        row_done = False
                        break
                    print(f"[{claim_no}] Draft {i}: Condition note OK")

                # ── Condition AFV ─────────────────────────────────────────
                _stage = f"draft_{i}_cond_afv"
                if aply_cond_afv == "Y":
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
                    if updt_frm_to_dt == "Y":
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

                    if chk_per_diem == "Y":
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
    """
    df = context.get("df")

    codes = load_code_refs(dx_code_ref_path)
    grid_price = codes.get("grid_price", {})

    system = win32com.client.Dispatch("EXTRA.System")
    sess   = system.ActiveSession
    screen = sess.Screen

    results = []

    for _, row_series in df.iterrows():
        row = {k: (str(v).strip() if v is not None else "") for k, v in row_series.to_dict().items()}
        claim_no = row.get("CLAIM_NO", "")

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
                results.append(row)
                send_pf(screen, 9)
                continue

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

            results.append(row)

        except Exception as exc:
            row["MACRO_STATUS"] = f"EXCEPTION: {type(exc).__name__}: {exc}"
            results.append(row)
            send_pf(screen, 9)

    return {"success": True, "result": results}
