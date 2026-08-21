"""
Claim Split HCFA — registered helper functions.

Mirrors release_pend_macro/helper.py's `release_pend_fetch_from_file`
shape: a small pipeline-entry function that reads a claim list from disk
into a DataFrame for claim_split_get_edi_details() to consume.

NOT ported here: release_pend_macro/helper.py also has
`release_pend_fetch_from_db` and `release_pend_send_status_to_db`, backed by
the `DailyInventory` / `ClaimsData` models and `bulk_upsert_claims` helper.
Those are shaped around release_pend's per-rule DENY/PAID/PEND decision
flow (RULE column, decision field, etc.), which claim_split_hcfa doesn't
have an equivalent of — there's no evidence in the VBA or the existing
Django models of what a claim-split-specific DB record should look like,
so wiring that up here would be guessing at a schema rather than porting
one. Add it the same way release_pend_macro's does once that's defined.
"""

import pandas as pd

from rule_engine.registry import register_function


@register_function(
    name="claim_split_fetch_from_file",
    tag="Claim Split HCFA",
    color="#6a3fb5",
    inputs=[{"name": "location", "type": "str"}],
    outputs=[{"name": "df", "type": "dataframe"}],
)
def claim_split_fetch_from_file(location: str, context=None):
    """
    Reads a claim list (xlsx / csv) from *location* and returns a DataFrame.

    Required column:
      CLAIM_NO

    Optional columns, only needed for SCRATCH / SCRATCH NOT ONLINE (mirror
    the hidden N:Q columns + cell O2 on the VBA MAIN sheet):
      NEW_CERT, NEW_CCN, NEW_DOS, NEWBORN_TYPE ("NEW BORN" / "NON-NEW BORN"
      / blank), NON_NEWBORN_SEQ
    """
    print(f"claim_split_fetch_from_file: reading {location}")
    if location.lower().endswith(".csv"):
        df = pd.read_csv(location, dtype=str).fillna("")
    else:
        df = pd.read_excel(location, dtype=str).fillna("")
    print(f"claim_split_fetch_from_file: {len(df)} rows loaded")
    return {"df": df}
