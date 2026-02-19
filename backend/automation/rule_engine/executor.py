from .models import RuleList, RuleEngine
from .registry import get_function


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

            result = function(**merged_params)

            if result:
                self.context.update(result)

            execution_log.append({
                "function": function_name,
                "params": params,
                "result": result
            })

        return execution_log
