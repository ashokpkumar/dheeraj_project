from rule_engine.registry import register_function

"""
string
integer
float
boolean
datetime
list
dict
any
"""
@register_function(
    name="load_claims", 
    inputs=[{"name": "client_id", "type": "string"}], # 
    outputs=[{"name": "claims", "type": "list"}]
)
def load_claims(client_id, context=None):

    claims = [
        {"id": 1, "amount": 100},
        {"id": 2, "amount": 200},
        {"id": 3, "amount": 20},
        {"id": 4, "amount": 50},
        {"id": 5, "amount": 900},
    ]

    return {"claims": claims}


@register_function(
    name="filter_claims",
    inputs=[
        {"name": "claims", "type": "list"},
        {"name": "min_amount", "type": "integer"}
    ],
    outputs=[{"name": "filtered_claims", "type": "list"}]
)
def filter_claims(claims, min_amount, context=None):

    result = [
        c for c in claims
        if c["amount"] >= min_amount
    ]

    return {"filtered_claims": result}
