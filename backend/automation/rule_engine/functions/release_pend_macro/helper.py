"""
Release / Pend Macro — registered helper functions.
Provides fetch (file / DB) and send-status-to-DB helpers
that plug into the rule-engine pipeline before/after the main batch.
"""

from datetime import datetime

import pandas as pd

from rule_engine.functions.helpers import bulk_upsert_claims
from rule_engine.models import RuleEngineProcessed
from rule_engine.registry import register_function


@register_function(
    name="release_pend_fetch_from_file",
    inputs=[{"name": "location", "type": "str"}],
    outputs=[{"name": "df", "type": "dataframe"}],
)
def release_pend_fetch_from_file(location: str, context=None):
    """
    Reads a claim workbook (xlsx / csv) from *location* and returns a DataFrame.

    Expected columns (matching the VBA grid column layout):
      CLAIM_NO, MACRO_STATUS, CLAIM_TYPE, PEND_CD, REL, DRAFTS, NEW_OV_AJ,
      NEW_OI_IND, NEW_AP_CD, OLD_PRV_CD, NEW_PRV_CD, OLD_POS, NEW_POS,
      OLD_TOS, NEW_TOS, OLD_INEL_CD, NEW_INEL_CD, BN_CODE, BN_QTY, DX_CD,
      NEW_OI_ELIG, NEW_OI_PD, COND_NT, TOD, TIME_UNITS, TIME_UNIT_STATUS,
      INT_NO, ZIP, AFV, NOTE_850, AP_CD_1ST, AP_CD_2ND, AMT_858,
      REMV_SPCFC_INEL, SEQ_NO, NEW_PLAN_ID, HIC_STAT, PROV_NAME, PROV_ADD,
      CITY, STATE, ZIP2, IRS, SPLIT_EE, SPLIT_PR, EOB_PER_CLM,
      INEL_SWITCH_VAL, STATE_TYPE, T_BILL, T_DISC, CERT_NO,
      NEW_OPI, CODED_OPI, FAIE_INEL_CD, PRE_CERT_NO
    """
    print(f"release_pend_fetch_from_file: reading {location}")
    if location.lower().endswith(".csv"):
        df = pd.read_csv(location, dtype=str).fillna("")
    else:
        df = pd.read_excel(location, dtype=str).fillna("")
    print(f"release_pend_fetch_from_file: {len(df)} rows loaded")
    return {"df": df}


@register_function(
    name="release_pend_fetch_from_db",
    inputs=[{"name": "rules", "type": "list"}],
    outputs=[{"name": "df", "type": "dataframe"}],
)
def release_pend_fetch_from_db(rules, context=None):
    """
    Fetches pending claims from the DailyInventory model filtered by *rules*.
    Returns a DataFrame with the same column layout expected by the macro.
    """
    import ast

    from django.db.models import Q

    from rule_engine.models import DailyInventory

    print(f"release_pend_fetch_from_db: fetching for rules {rules}")
    rule_list = ast.literal_eval(rules) if isinstance(rules, str) else list(rules)

    qs = (
        DailyInventory.objects
        .filter(MACRO_RULE__in=rule_list)
        .values(
            "CLAIM_NO",
            "CLAIM_TYPE",
            "PEND_CD",
            "DRAFTS",
            "CERT_NO",
        )
        .distinct()
    )

    df = pd.DataFrame(list(qs)).fillna("")
    print(f"release_pend_fetch_from_db: {len(df)} rows returned")
    return {"df": df}


@register_function(
    name="release_pend_send_status_to_db",
    inputs=[],
    outputs=[],
)
def release_pend_send_status_to_db(context=None):
    """
    Persists the macro run results stored in context['result'] to the database
    via RuleEngineProcessed and the bulk_upsert_claims helper.
    """
    results      = context.get("result")
    rule_name    = context.get("rule_name")
    rule_engine_id = context.get("rule_engine_id")
    manual       = context.get("manual")

    print(f"release_pend_send_status_to_db: saving {len(results) if results else 0} records")

    processed = RuleEngineProcessed.objects.create(
        rule_engine_id=rule_engine_id,
        rule_name=rule_name,
        processed_at=datetime.now(),
        claims_count=len(results) if results else 0,
    )

    if results:
        upsert_result = bulk_upsert_claims(results, rule_name, manual, processed.id)
        print(upsert_result)
