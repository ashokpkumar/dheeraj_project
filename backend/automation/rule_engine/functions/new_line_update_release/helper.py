"""
NEW.LINE.UPDATE.RELEASE Macro — fetch / persist helpers.
Mirrors release_pend_macro/helper.py's release_pend_fetch_from_file and
release_pend_send_status_to_db.
"""

from datetime import datetime

import pandas as pd

from rule_engine.functions.helpers import bulk_upsert_claims
from rule_engine.models import RuleEngineProcessed
from rule_engine.registry import register_function


@register_function(
    name="new_line_update_release_fetch_from_file",
    tag="New Line Update Release",
    color="#e65100",
    inputs=[{"name": "location", "type": "str"}],
    outputs=[{"name": "df", "type": "dataframe"}],
)
def new_line_update_release_fetch_from_file(location: str, context=None):
    """
    Reads the NEW.LINE.UPDATE.RELEASE work list (xlsx / csv) from *location*
    and returns a DataFrame — one row per SERVICE LINE, matching
    new_line_update_release_input_template.csv. Feed this node's output
    into new_line_update_release_run_batch (directly, or via
    new_line_update_medicare_oi_calc / new_line_update_mru_repricing_calc
    first if those columns need to be calculated rather than supplied).

    Expected columns:
      CLAIM_NO, RULE, ROUTE_TO_OPID, NEW_PRV_VAL,               (claim-level, carried on every line of the claim)
      BGN_SV_DT, CPT, LINE_CHG_AMT, UNITS, MOD01, MOD02, MOD03, (match criteria — blank = don't care)
      AP, NEW_INEL1_AMOUNT, NEW_INEL1_CD, NEW_INEL2_AMOUNT, NEW_INEL2_CD,
      NEW_MOD01, NEW_MOD02, NEW_MOD03, SMB_ADJ_AMT, SMB_ADJ_REASON,
      OI_ELIG_AMT, OI_PAID_AMT, OI_TYPE, BU, IU, OC, PROV_RATE,
      NEW_BGN, NEW_END, NEW_TOS, NEW_CHRG_AMT, BN_QTY, BN_AMT
    """
    print(f"new_line_update_release_fetch_from_file: reading {location}")
    if location.lower().endswith(".csv"):
        df = pd.read_csv(location, dtype=str).fillna("")
    else:
        df = pd.read_excel(location, dtype=str).fillna("")
    print(f"new_line_update_release_fetch_from_file: {len(df)} rows loaded")
    return {"df": df}


@register_function(
    name="new_line_update_release_send_status_to_db",
    tag="New Line Update Release",
    color="#e65100",
    inputs=[],
    outputs=[],
)
def new_line_update_release_send_status_to_db(context=None):
    """
    Persists the macro run results stored in context['result'] to the database
    via RuleEngineProcessed and the bulk_upsert_claims helper. Mirrors
    release_pend_send_status_to_db — new_line_update_release_run_batch's
    result rows are already shaped as {"CLAIM CONTROL #": ..., "MACRO STATUS": ...},
    the same keys bulk_upsert_claims expects.
    """
    results        = context.get("result")
    rule_name      = context.get("rule_name")
    rule_engine_id = context.get("rule_engine_id")
    manual         = context.get("manual")

    print(f"new_line_update_release_send_status_to_db: saving {len(results) if results else 0} records")

    processed = RuleEngineProcessed.objects.create(
        rule_engine_id=rule_engine_id,
        rule_name=rule_name,
        processed_at=datetime.now(),
        claims_count=len(results) if results else 0,
    )

    if results:
        upsert_result = bulk_upsert_claims(results, rule_name, manual, processed.id)
        print(upsert_result)
