"""
Same Day Reversal macro — registered helper functions.
Provides a fetch (file) and send-status-to-DB helper that plug into the
rule-engine pipeline before/after the main batch.
"""

from datetime import datetime

import pandas as pd

from rule_engine.functions.helpers import bulk_upsert_claims
from rule_engine.models import RuleEngineProcessed
from rule_engine.registry import register_function


@register_function(
    name="same_day_reversal_fetch_from_file",
    tag="Same Day Reversal",
    color="#6a1b9a",
    inputs=[{"name": "location", "type": "str"}],
    outputs=[{"name": "df", "type": "dataframe"}],
)
def same_day_reversal_fetch_from_file(location: str, context=None):
    """
    Reads a claim workbook (xlsx / csv) from *location* and returns a
    DataFrame. Expected columns (mirrors sheet columns A / B / D):
      CCN, CERT_ID, BG_SV_DT
    """
    print(f"same_day_reversal_fetch_from_file: reading {location}")
    if location.lower().endswith(".csv"):
        df = pd.read_csv(location, dtype=str).fillna("")
    else:
        df = pd.read_excel(location, dtype=str).fillna("")
    print(f"same_day_reversal_fetch_from_file: {len(df)} rows loaded")
    return {"df": df}


@register_function(
    name="same_day_reversal_send_status_to_db",
    tag="Same Day Reversal",
    color="#6a1b9a",
    inputs=[],
    outputs=[],
)
def same_day_reversal_send_status_to_db(context=None):
    """
    Persists the macro run results stored in context['result'] to the
    database via RuleEngineProcessed and the bulk_upsert_claims helper.
    """
    results = context.get("result")
    rule_name = context.get("rule_name")
    rule_engine_id = context.get("rule_engine_id")
    manual = context.get("manual")

    print(f"same_day_reversal_send_status_to_db: saving {len(results) if results else 0} records")

    processed = RuleEngineProcessed.objects.create(
        rule_engine_id=rule_engine_id,
        rule_name=rule_name,
        processed_at=datetime.now(),
        claims_count=len(results) if results else 0,
    )

    if results:
        upsert_result = bulk_upsert_claims(results, rule_name, manual, processed.id)
        print(upsert_result)
