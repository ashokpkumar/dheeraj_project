"""
NEW.LINE.UPDATE.RELEASE — Medicare OI calculation.
Ports MEDICARE_CALCULATION / RTN_ELIG_AMT / RTN_OIPAID_AMT / MED_CALC_SETTINGS
from Macro/oWauben.txt (cmdMedCalc_Click in Macro/Main.txt).

Pure calculation — no emulator/screen interaction, so it can run as its own
pipeline step ahead of new_line_update_release_run_batch, populating
OI_ELIG_AMT / OI_PAID_AMT on the service-line rows the release step reads.
"""

import pandas as pd

from rule_engine.registry import register_function

from .utils import load_line_update_reference


def _rtn_elig_amt(chrg_amt) -> float:
    chrg_amt = str(chrg_amt or "").strip()
    if not chrg_amt:
        return 0.0
    try:
        return float(chrg_amt)
    except (TypeError, ValueError):
        return 0.0


def _rtn_oi_paid_amt(t_billed_less_md_pd_b4chk, t_md_ded_coin, pct_chrg, oi_elig_amt, i):
    if i > 1:
        return round(oi_elig_amt * pct_chrg, 2)
    if t_billed_less_md_pd_b4chk == t_md_ded_coin:
        return round(oi_elig_amt * pct_chrg, 2)
    if t_billed_less_md_pd_b4chk < t_md_ded_coin:
        return round(oi_elig_amt * pct_chrg, 2) - (t_md_ded_coin - t_billed_less_md_pd_b4chk)
    return round(oi_elig_amt * pct_chrg, 2) + (t_billed_less_md_pd_b4chk - t_md_ded_coin)


def _calc_claim(lines: list, oi_type: str, med_calc: dict) -> str:
    """Mutates `lines` (dict rows for one claim) in place. Returns claim status."""
    for ln in lines:
        ln["OI_ELIG_AMT"] = ""
        ln["OI_PAID_AMT"] = ""
        ln["OI_TYPE"] = ""

    claim_no = str(lines[0].get("CLAIM_NO", "")).strip()
    if claim_no not in med_calc:
        return "NO MED CALC SET."

    ded_coin_eob, neg_contractual, noncov = med_calc[claim_no]

    t_billed = 0.0
    for ln in lines:
        try:
            t_billed += float(str(ln.get("LINE_CHG_AMT", "") or 0).strip() or 0)
        except (TypeError, ValueError):
            pass

    try:
        t_billed_less_noncov = t_billed - float(noncov or 0)
    except (TypeError, ValueError):
        t_billed_less_noncov = t_billed

    # NOTE: ported as-written from the VBA (MEDICARE_CALCULATION). This
    # comparison only passes when the reference's NON-COVERED AMT is 0 —
    # subtracting any non-zero noncov amount makes t_billed_less_noncov
    # differ from t_billed by definition. This looks like a pre-existing
    # bug/edge-case in the source macro (kept for parity); flag to business
    # before relying on non-zero NON-COVERED AMT values.
    if t_billed != t_billed_less_noncov:
        return "MED CALC AMT FAILED."

    try:
        t_md_ded_coin = round(float(ded_coin_eob or 0), 2)
    except (TypeError, ValueError):
        t_md_ded_coin = 0.0

    if t_billed_less_noncov == 0:
        return "MED CALC AMT FAILED."
    pct_chrg = round(1 - (t_md_ded_coin / t_billed_less_noncov), 9)

    if oi_type == "TYPE B":
        t_md_pd_b4_check = 0.0
        for ln in lines:
            ln["OI_ELIG_AMT"] = _rtn_elig_amt(ln.get("LINE_CHG_AMT"))
            t_md_pd_b4_check += round(ln["OI_ELIG_AMT"] * pct_chrg, 2)

        t_billed_less_md_pd_b4_check = t_billed - t_md_pd_b4_check
        for i, ln in enumerate(lines, start=1):
            ln["OI_PAID_AMT"] = round(
                _rtn_oi_paid_amt(t_billed_less_md_pd_b4_check, t_md_ded_coin, pct_chrg, ln["OI_ELIG_AMT"], i), 2
            )
        return "OK"

    # Other OI types are not implemented in the source VBA (only "TYPE B"
    # has a Select Case branch) — left as a no-op for parity.
    return "OI TYPE NOT IMPLEMENTED"


@register_function(
    name="new_line_update_medicare_oi_calc",
    tag="New Line Update Release",
    color="#e65100",
    inputs=[
        {"name": "reference_path", "type": "str"},
        {"name": "oi_type", "type": "str", "options": ["TYPE B"], "default": "TYPE B"},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "df", "type": "dataframe"},
        {"name": "result", "type": "list"},
    ],
)
def new_line_update_medicare_oi_calc(reference_path: str, oi_type: str = "TYPE B", context=None):
    """
    Mirrors cmdMedCalc_Click + MEDICARE_CALCULATION.
    Groups context['df'] (service-line rows) by CLAIM_NO and, for claims
    found in the reference file's MED_CALC table, fills in OI_ELIG_AMT /
    OI_PAID_AMT per line. Returns the updated rows so a downstream
    new_line_update_release_run_batch step can pick them up.
    """
    if context is None:
        return {"success": False, "df": None, "result": [], "error": "context is None"}

    df = context.get("df")
    if df is None or df.empty:
        return {"success": True, "df": df, "result": []}

    ref = load_line_update_reference(reference_path)
    med_calc = ref["med_calc"]

    rows = [{k: ("" if v is None else str(v).strip()) for k, v in r.items()} for r in df.to_dict("records")]

    claims = {}
    for row in rows:
        claims.setdefault(str(row.get("CLAIM_NO", "")).strip(), []).append(row)

    result = []
    for claim_no, lines in claims.items():
        status = _calc_claim(lines, oi_type, med_calc)
        result.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": status})

    updated_df = pd.DataFrame(rows)
    return {"success": True, "df": updated_df, "result": result}
