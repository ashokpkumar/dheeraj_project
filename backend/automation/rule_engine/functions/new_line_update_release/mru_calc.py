"""
NEW.LINE.UPDATE.RELEASE — MRU repricing calculation.
Ports cdmMRU_Click (Macro/Main.txt) + MRU_CALC_SETTINGS (Macro/oWauben.txt).

Pure calculation — no emulator/screen interaction. Matches each service-line
row against the MRU REPRICING INFO table (mru_info_path) on CLAIM_NO +
whichever of BGN_SV_DT / CPT / LINE_CHG_AMT / UNITS / MOD01-03 are populated
on the row (blank fields are "don't care", same as the VBA AutoFilter
chain), then reprices NEW_INEL1_AMOUNT off the IP%/OUT% reference rate for
that repricing row's year + state, based on whether its POS is in-network.
"""

import pandas as pd

from rule_engine.registry import register_function

from .utils import is_it_matching, load_line_update_reference


def _match_mru_rows(mru_rows: list, ln: dict) -> list:
    matches = []
    for mru in mru_rows:
        if str(mru.get("CLAIM_NO", "")).strip() != str(ln.get("CLAIM_NO", "")).strip():
            continue
        bgn = str(ln.get("BGN_SV_DT", "") or "").strip()
        if bgn and not is_it_matching(bgn, mru.get("BGN_SV_DT", "")):
            continue
        cpt = str(ln.get("CPT", "") or "").strip()
        if cpt and not is_it_matching(cpt, mru.get("CPT", "")):
            continue
        chrg = str(ln.get("LINE_CHG_AMT", "") or "").strip()
        if chrg and not is_it_matching(chrg, mru.get("LINE_CHG_AMT", "")):
            continue
        units = str(ln.get("UNITS", "") or "").strip()
        if units and not is_it_matching(units, mru.get("UNITS", "")):
            continue
        for mod_key in ("MOD01", "MOD02", "MOD03"):
            mod_val = str(ln.get(mod_key, "") or "").strip()
            if mod_val and not is_it_matching(mod_val, mru.get(mod_key, "")):
                break
        else:
            matches.append(mru)
    return matches


@register_function(
    name="new_line_update_mru_repricing_calc",
    tag="New Line Update Release",
    color="#e65100",
    inputs=[
        {"name": "mru_info_path", "type": "str"},
        {"name": "reference_path", "type": "str"},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "df", "type": "dataframe"},
        {"name": "result", "type": "list"},
    ],
)
def new_line_update_mru_repricing_calc(mru_info_path: str, reference_path: str, context=None):
    """
    Mirrors cdmMRU_Click. Reads the MRU REPRICING INFO table from
    mru_info_path (columns: CLAIM_NO, BGN_SV_DT, CPT, LINE_CHG_AMT, UNITS,
    MOD01, MOD02, MOD03, POS, PRV — PRV holds the 2-letter state code used
    for the rate lookup, per the source VBA key = Year(BGN_SV_DT) + PRV).
    Fills NEW_INEL1_AMOUNT on context['df'] (service-line rows) in place.
    """
    if context is None:
        return {"success": False, "df": None, "result": [], "error": "context is None"}

    df = context.get("df")
    if df is None or df.empty:
        return {"success": True, "df": df, "result": []}

    if mru_info_path.lower().endswith(".csv"):
        mru_df = pd.read_csv(mru_info_path, dtype=str).fillna("")
    else:
        mru_df = pd.read_excel(mru_info_path, dtype=str).fillna("")
    mru_df.columns = [str(c).strip().upper() for c in mru_df.columns]
    mru_rows = mru_df.to_dict("records")

    ref = load_line_update_reference(reference_path)
    mru_calc = ref["mru_calc"]
    innetwork_pos = ref["mru_innetwork_pos"]

    rows = [{k: ("" if v is None else str(v).strip()) for k, v in r.items()} for r in df.to_dict("records")]

    result = []
    for ln in rows:
        claim_no = str(ln.get("CLAIM_NO", "")).strip()
        ln["NEW_INEL1_AMOUNT"] = ""
        matches = _match_mru_rows(mru_rows, ln)
        if len(matches) != 1:
            result.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": "UNABLE TO CALCULATE"})
            continue

        mru = matches[0]
        try:
            year = str(pd.to_datetime(mru.get("BGN_SV_DT", "")).year)
        except Exception:
            year = ""
        prv = str(mru.get("PRV", "") or "").strip()
        key = f"{year}{prv}"

        if key not in mru_calc:
            result.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": "NO MRU CALC SET"})
            continue

        ip_pct, out_pct = mru_calc[key]
        pos = str(mru.get("POS", "") or "").strip().zfill(2)
        pct = ip_pct if pos in innetwork_pos else out_pct
        try:
            amt = round(float(str(mru.get("LINE_CHG_AMT", "") or 0)) * pct, 2)
        except (TypeError, ValueError):
            amt = 0.0
        ln["NEW_INEL1_AMOUNT"] = f"{amt:.2f}"
        result.append({"CLAIM CONTROL #": claim_no, "MACRO STATUS": "OK", "NEW_INEL1_AMOUNT": ln["NEW_INEL1_AMOUNT"]})

    updated_df = pd.DataFrame(rows)
    return {"success": True, "df": updated_df, "result": result}
