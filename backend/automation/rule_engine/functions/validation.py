from rule_engine.registry import register_function


# Validate claim has required fields
@register_function(
    name="validate_required_fields",
    inputs=[
        {"name": "claims", "type": "list"},
        {"name": "required_fields", "type": "list"}
    ],
    outputs=[
        {"name": "valid_claims", "type": "list"},
        {"name": "invalid_claims", "type": "list"}
    ]
)
def validate_required_fields(claims, required_fields, context=None):

    valid_claims = []
    invalid_claims = []

    for claim in claims:

        missing = [
            field for field in required_fields
            if field not in claim or claim[field] is None
        ]

        if missing:
            claim["_validation_error"] = f"Missing fields: {missing}"
            invalid_claims.append(claim)
        else:
            valid_claims.append(claim)

    return {
        "valid_claims": valid_claims,
        "invalid_claims": invalid_claims
    }


# Validate claim amount range
@register_function(
    name="validate_claim_amount_range",
    inputs=[
        {"name": "claims", "type": "list"},
        {"name": "min_amount", "type": "float"},
        {"name": "max_amount", "type": "float"}
    ],
    outputs=[
        {"name": "valid_claims", "type": "list"},
        {"name": "invalid_claims", "type": "list"}
    ]
)
def validate_claim_amount_range(claims, min_amount, max_amount, context=None):

    valid_claims = []
    invalid_claims = []

    for claim in claims:

        amount = claim.get("amount", 0)

        if min_amount <= amount <= max_amount:
            valid_claims.append(claim)
        else:
            claim["_validation_error"] = "Amount out of range"
            invalid_claims.append(claim)

    return {
        "valid_claims": valid_claims,
        "invalid_claims": invalid_claims
    }


# Remove duplicate claims based on claim_id
@register_function(
    name="deduplicate_claims",
    inputs=[
        {"name": "claims", "type": "list"},
        {"name": "unique_field", "type": "string"}
    ],
    outputs=[
        {"name": "unique_claims", "type": "list"},
        {"name": "duplicate_claims", "type": "list"}
    ]
)
def deduplicate_claims(claims, unique_field, context=None):

    seen = set()

    unique_claims = []
    duplicate_claims = []

    for claim in claims:

        key = claim.get(unique_field)

        if key in seen:
            claim["_validation_error"] = "Duplicate claim"
            duplicate_claims.append(claim)
        else:
            seen.add(key)
            unique_claims.append(claim)

    return {
        "unique_claims": unique_claims,
        "duplicate_claims": duplicate_claims
    }


# Filter claims by status
@register_function(
    name="filter_claims_by_status",
    inputs=[
        {"name": "claims", "type": "list"},
        {"name": "allowed_status", "type": "list"}
    ],
    outputs=[
        {"name": "filtered_claims", "type": "list"}
    ]
)
def filter_claims_by_status(claims, allowed_status, context=None):

    filtered = [
        claim for claim in claims
        if claim.get("status") in allowed_status
    ]

    return {
        "filtered_claims": filtered
    }


# Enrich claim with computed tax
@register_function(
    name="calculate_claim_tax",
    inputs=[
        {"name": "claims", "type": "list"},
        {"name": "tax_rate", "type": "float"}
    ],
    outputs=[
        {"name": "claims_with_tax", "type": "list"}
    ]
)
def calculate_claim_tax(claims, tax_rate, context=None):

    result = []

    for claim in claims:

        amount = claim.get("amount", 0)

        tax = amount * tax_rate

        claim["tax"] = tax

        result.append(claim)

    return {
        "claims_with_tax": result
    }


# Approve claims automatically under threshold
@register_function(
    name="auto_approve_claims",
    inputs=[
        {"name": "claims", "type": "list"},
        {"name": "approval_threshold", "type": "float"}
    ],
    outputs=[
        {"name": "approved_claims", "type": "list"},
        {"name": "manual_review_claims", "type": "list"}
    ]
)
def auto_approve_claims(claims, approval_threshold, context=None):

    approved = []
    manual = []

    for claim in claims:

        if claim.get("amount", 0) <= approval_threshold:

            claim["status"] = "approved"

            approved.append(claim)

        else:

            claim["status"] = "manual_review"

            manual.append(claim)

    return {
        "approved_claims": approved,
        "manual_review_claims": manual
    }


# Merge two claim lists
@register_function(
    name="merge_claim_lists",
    inputs=[
        {"name": "claims_a", "type": "list"},
        {"name": "claims_b", "type": "list"}
    ],
    outputs=[
        {"name": "merged_claims", "type": "list"}
    ]
)
def merge_claim_lists(claims_a, claims_b, context=None):

    return {
        "merged_claims": claims_a + claims_b
    }
