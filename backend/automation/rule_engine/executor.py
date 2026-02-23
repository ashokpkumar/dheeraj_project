from collections import deque
from .models import RuleList, RuleEdge
from .registry import get_function
import inspect


class GraphRuleExecutor:

    def __init__(self, rule_engine_id):
        self.rule_engine_id = rule_engine_id
        self.context = {}
        self.execution_log = []

    def execute(self):

        nodes = {
            node.id: node
            for node in RuleList.objects.filter(
                rule_engine_id=self.rule_engine_id
            )
        }

        edges = RuleEdge.objects.filter(
            rule_engine_id=self.rule_engine_id
        )

        # Build adjacency list
        adj = {}
        incoming = set()

        for edge in edges:
            adj.setdefault(edge.source_id, []).append(edge)
            incoming.add(edge.target_id)

        # Start nodes = no incoming edges
        start_nodes = [
            node for node_id, node in nodes.items()
            if node_id not in incoming
        ]

        queue = deque(start_nodes)

        while queue:

            node = queue.popleft()

            result = self.execute_node(node)

            for edge in adj.get(node.id, []):

                if self.evaluate_condition(edge.condition):
                    queue.append(edge.target)

        return self.execution_log

    def execute_node(self, node):

        function = get_function(node.rule_logic.function_name)

        params = node.params or {}
        merged = {**self.context, **params}

        sig = inspect.signature(function)

        valid = {
            k: v for k, v in merged.items()
            if k in sig.parameters
        }

        if "context" in sig.parameters:
            valid["context"] = self.context

        result = function(**valid)

        if result:
            self.context.update(result)

        self.execution_log.append({
            "node": node.id,
            "function": node.rule_logic.function_name,
            "result": result,
            "context_after": self.context.copy()
        })

        return result

    def evaluate_condition(self, condition):

        if not condition:
            return True

        try:
            return eval(condition, {}, self.context)
        except Exception:
            return False