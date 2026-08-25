"""
Claim Split HCFA — registered helper functions.

`claim_split_fetch_from_file` mirrors release_pend_macro/helper.py's
`release_pend_fetch_from_file` shape: a small pipeline-entry function that
reads a claim list from disk into a DataFrame for claim_split_get_edi_details()
to consume.

`claim_split_fetch_from_db` / `claim_split_send_status_to_db` port
release_pend_macro/helper.py's `release_pend_fetch_from_db` /
`release_pend_send_status_to_db` — backed by the `DailyInventory` /
`ClaimsData` models and `bulk_upsert_claims` helper, same as there. Unlike
release_pend (which keys off a RULE column), claim_split_hcfa's unit of
work is the CCN (Claim Control Number — MAIN sheet column C, `CLAIM_NO`
downstream), so the fetch is keyed off a list of CCNs instead of rules,
matched against DailyInventory.MCRFM_ROLL_CD — the same field
`fetch_claim_ids_from_db()` in db_function.py treats as the claim id.

The store side captures everything claim_split_get_edi_details()/
claim_split_run_batch() produced for a claim (all ClaimInfo/
ClaimServiceLInes-derived fields, plus the split result) into
ClaimsData.details (JSONField) — bulk_upsert_claims's status/decision
columns alone can't hold a whole extracted claim, and claims_df rows use
claim_split_hcfa's own CLAIM_NO/MACRO_STATUS field names rather than the
"CLAIM CONTROL #"/"MACRO STATUS" shape bulk_upsert_claims expects
(the convention release_pend_macro, same_day_reversal, OI_YES_NO, and
new_line_update_release all use), so this translates before calling it.
"""

from datetime import datetime

import pandas as pd

from rule_engine.functions.helpers import bulk_upsert_claims
from rule_engine.models import RuleEngineProcessed
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


@register_function(
    name="claim_split_fetch_from_db",
    tag="Claim Split HCFA",
    color="#6a3fb5",
    inputs=[{"name": "ccns", "type": "list"}],
    outputs=[{"name": "df", "type": "dataframe"}],
)
def claim_split_fetch_from_db(ccns, context=None):
    """
    Fetches the claims to split from the DailyInventory model, filtered by
    CCN (MCRFM_ROLL_CD). Returns a DataFrame with a CLAIM_NO column — the
    only column claim_split_get_edi_details() requires (each must be
    exactly 11 characters, same gate as the VBA's `Len(CCN) <> 11`).

    *ccns* may be a real list, or a stringified one (e.g. from a UI text
    field) — same `ast.literal_eval` fallback release_pend_fetch_from_db
    uses for *rules*.
    """
    import ast

    from rule_engine.models import DailyInventory

    print(f"claim_split_fetch_from_db: fetching for CCN(s) {ccns}")
    ccn_list = ast.literal_eval(ccns) if isinstance(ccns, str) else list(ccns)
    ccn_list = [str(c).strip() for c in ccn_list if str(c).strip()]

    roll_codes = (
        DailyInventory.objects
        .filter(MCRFM_ROLL_CD__in=ccn_list)
        .values_list("MCRFM_ROLL_CD", flat=True)
        .distinct()
    )

    df = pd.DataFrame({"CLAIM_NO": list(roll_codes)}, dtype=str).fillna("")
    print(f"claim_split_fetch_from_db: {len(df)} row(s) returned")
    return {"df": df}


@register_function(
    name="claim_split_send_status_to_db",
    tag="Claim Split HCFA",
    color="#6a3fb5",
    inputs=[],
    outputs=[{"name": "success", "type": "bool"}, {"name": "saved", "type": "int"}],
)
def claim_split_send_status_to_db(context=None):
    """
    Persists this run's results to the database — one ClaimsData row per
    claim, via RuleEngineProcessed + bulk_upsert_claims (same pattern as
    release_pend_send_status_to_db).

    Reads context['claims_df'] and context['service_lines_df'] (from
    claim_split_get_edi_details) and, if the pipeline chained through it,
    context['result'] (from claim_split_run_batch). ClaimsData.details
    ends up holding the full claims_df row for that claim plus its service
    lines and split result — i.e. everything captured in the CSV/Excel
    output, not just a status string.
    """
    claims = context.get("claims_df") or []
    service_lines = context.get("service_lines_df") or []
    split_results = context.get("result") or []

    rule_name = context.get("rule_name")
    rule_engine_id = context.get("rule_engine_id")
    manual = context.get("manual")

    print(f"claim_split_send_status_to_db: saving {len(claims)} claim(s)")

    lines_by_claim: dict[str, list[dict]] = {}
    for svl in service_lines:
        lines_by_claim.setdefault(svl.get("CLAIM_NO", ""), []).append(svl)

    split_by_claim = {r.get("CLAIM_NO", ""): r for r in split_results}

    rows = []
    for claim_row in claims:
        claim_no = claim_row.get("CLAIM_NO", "")
        split_row = split_by_claim.get(claim_no, {})
        status = split_row.get("MACRO_STATUS") or claim_row.get("MACRO_STATUS", "")
        details = dict(claim_row)
        details["SERVICE_LINES"] = lines_by_claim.get(claim_no, [])
        if split_row:
            details["SPLIT_RESULT"] = split_row
        rows.append({
            "CLAIM CONTROL #": claim_no,
            "MACRO STATUS": status,
            "DECISION": claim_row.get("CLAIM_TYPE", ""),
            "DETAILS": details,
        })

    processed = RuleEngineProcessed.objects.create(
        rule_engine_id=rule_engine_id,
        rule_name=rule_name,
        processed_at=datetime.now(),
        claims_count=len(rows),
    )

    if rows:
        upsert_result = bulk_upsert_claims(rows, rule_name, manual, processed.id)
        print(upsert_result)

    return {"success": True, "saved": len(rows)}
