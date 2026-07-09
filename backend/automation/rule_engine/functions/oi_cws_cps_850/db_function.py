from datetime import datetime

from rule_engine.functions.helpers import bulk_upsert_claims
from rule_engine.models import DailyInventory, RuleEngineProcessed,RuleEngine,ClaimsData
from rule_engine.registry import register_function
from django.db.models import Q
from django.apps import apps
import ast 
# from scheduler_old.models import DailyInventory, DateFileData


@register_function(
    name="fetch_claim_ids_from_db", 
    inputs=[{"name": "rules", "type": "list"}], # 
    outputs=[{"name": "claim_ids", "type": "list"}]
)
def fetch_claim_ids_from_db( rules,context=None):
    print(f"Started fetch claims for {rules}")
    completed_claims = ClaimsData.objects.filter(Q(status__contains='DONE')).all()
    completed_claims_ids = [claims.claims_id for claims in completed_claims]
    roll_codes = list(
        DailyInventory.objects
            .filter(Q(MACRO_RULE__in=ast.literal_eval(rules))
                    # &
                    # ~Q(MCRFM_ROLL_CD__in=completed_claims_ids)
                    )
            .values_list('MCRFM_ROLL_CD', flat=True)
            .distinct()[:100]
    )
    print(f"completed fetch claims {len(roll_codes)}")
    return {"claim_ids":roll_codes}


@register_function(
    name="add_scrapped_values_to_db", 
    inputs=[{"name": "rule_name", "type": "string"}], # 
    outputs=[]
)
def add_scrapped_values_to_db( rule_name:str,context=None):
    print("Scrapped values to db")

    results = context.get("scrapped_claims")

    engine = RuleEngine.objects.filter(rule_name = rule_name).first()

    rule_engine_processed = RuleEngineProcessed.objects.create(rule_engine_id = engine.id,
                                                               rule_name = engine.rule_name,
                                                                processed_at = datetime.now(),
                                                                    claims_count = len(results)
                                       )
    upsert_result = bulk_upsert_claims(results,rule_name,context.get('manual'),rule_engine_processed.id)
    print(upsert_result)
