



from datetime import datetime

from rule_engine.functions.helpers import bulk_upsert_claims
from rule_engine.models import ClaimsData, DailyInventory, RuleEngineProcessed
from rule_engine.registry import register_function
import pandas as pd
import ast 

from django.db.models import Q
import ast
import pandas as pd
from django.db.models import Q

@register_function(
    name="oi_yes_fetch_cert_id_seq_from_db",
    tag="OI Yes NO",
    color="#1565c0",
    inputs=[{"name": "rules", "type": "list"}],
    outputs=[{"name": "df", "type": "dataframe"}]  # <-- updated output
)
def oi_yes_fetch_cert_id_seq_from_db(rules, context=None):
    print(f"Started fetch claims for rules: {rules}")

    # Fetch completed claims (kept if needed later; otherwise can be removed)

    # Fetch only required columns from DailyInventory
    inventory_qs = (
        DailyInventory.objects
        .filter(MACRO_RULE__in=ast.literal_eval(rules))
        .values(
            'MCRFM_ROLL_CD',
            'INDIV_SEQ_NBR',
            'ENRL_CERT_NBR'
        )
        .distinct()[:10]
    )

    # Convert queryset → DataFrame
    df = pd.DataFrame(list(inventory_qs))

    print(f"Completed fetch. Rows returned: {len(df)}")

    return {"df": df}



@register_function(
    name="oi_yes_fetch_File_from_folder", 
    tag="OI Yes NO",
    color="#1565c0",
    inputs=[{"name": "location", "type": "str"}], # 
    outputs=[{"name": "df", "type": "DataFrame"}]
)
def oi_yes_fetch_File_from_folder( location,context=None):
    print(f"fetching data from Folder {location}")
    df = pd.read_excel(location)
    return {"df":df}



@register_function(
    name="oi_yes_send_status_to_db", 
    tag="OI Yes NO",
    color="#1565c0",
    inputs=[], # 
    outputs=[]
)
def oi_yes_send_status_to_db( context=None):
    print("sending OI status to DB")
    results = context.get("result")
    rule_name = context.get("rule_name")
    rule_engine_id = context.get("rule_engine_id")
    # engine = RuleEngine.objects.filter(rule_name = rule_name).first()

    rule_engine_processed = RuleEngineProcessed.objects.create(rule_engine_id = rule_engine_id,
                                                               rule_name = rule_name,
                                                                processed_at = datetime.now(),
                                                                    claims_count = len(results) if results else 0
                                       )
    if results and len(results)!=0:
        upsert_result = bulk_upsert_claims(results,rule_name,context.get('manual'),rule_engine_processed.id)
        print(upsert_result)


