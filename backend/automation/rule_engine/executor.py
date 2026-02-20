from .models import RuleList, RuleEngine
from .registry import get_function

import inspect

class RuleExecutor:

    def __init__(self, rule_engine_id):

        self.rule_engine_id = rule_engine_id

        self.context = {}

    def execute(self):

        rules = RuleList.objects.filter(
            rule_engine_id=self.rule_engine_id
        ).order_by("rule_function_order")

        execution_log = []

        for rule in rules:

            function_name = rule.rule_logic.function_name

            function = get_function(function_name)

            params = rule.params or {}

            merged_params = {
                **self.context,
                **params
            }

            # ✅ FILTER PARAMS BASED ON FUNCTION SIGNATURE
            sig = inspect.signature(function)

            valid_params = {
                key: value
                for key, value in merged_params.items()
                if key in sig.parameters
            }

            # optional: pass context if function accepts it
            if "context" in sig.parameters:
                valid_params["context"] = self.context

            # execute function safely
            result = function(**valid_params)

            # update context with outputs
            if result and isinstance(result, dict):
                self.context.update(result)

            execution_log.append({
                "function": function_name,
                "inputs": valid_params,
                "output": result,
                "context_after": self.context.copy()
            })

        return execution_log
