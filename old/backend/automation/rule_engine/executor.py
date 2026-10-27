from collections import deque
import inspect
import multiprocessing
from multiprocessing import Process, Queue
import django
import os


def _execute_in_separate_process_worker(rule_engine_id, queue):
    """Worker function to execute the workflow in a separate process with Django setup"""
    try:
        # Setup Django in the child process FIRST
        django.setup()
        
        # Import models AFTER django.setup()
        from .models import RuleEngine, RuleList, RuleEdge
        
        executor = GraphRuleExecutor(rule_engine_id, manual=False)
        result = executor._execute_workflow()
        queue.put(result)
    except Exception as e:
        print(f"Error in separate process: {e}")
        import traceback
        traceback.print_exc()
        queue.put([])


class GraphRuleExecutor:

    def __init__(self, rule_engine_id, manual):
        self.rule_engine_id = rule_engine_id
        self.context = {"manual": manual}
        self.execution_log = []

    def execute(self):
        # Check if running in manual mode
        #self.context["manual"]=False
        if not self.context.get("manual"):
            # Run in separate process for automated execution
            queue = Queue()
            process = Process(target=_execute_in_separate_process_worker, args=(self.rule_engine_id, queue))
            process.start()
            process.join()  # Wait for process to complete
            
            if not queue.empty():
                self.execution_log = queue.get()
            
            return self.execution_log
        else:
            # Run in current process for manual execution
            return self._execute_workflow()

    def _execute_workflow(self):
        """The actual execution logic that can run in current or separate process"""
        from .models import RuleEngine, RuleList, RuleEdge
        
        # is_active = RuleEngine.objects.filter(id=self.rule_engine_id, is_active=True).exists()
        # if not is_active:
        #     print(f"RuleEngine {self.rule_engine_id} is not active. Exiting execution.")
        #     raise Exception(f"RuleEngine {self.rule_engine_id} is not active Hence Exiting")
        
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
        from .models import RuleEngine
        from .registry import get_function
        
        function = get_function(node.function_name)
        print(f"function_name {function}")
        if not self.context.get("rule_name"):
            rule_engine = RuleEngine.objects.filter(id=self.rule_engine_id).first()
            self.context['rule_engine_id']=self.rule_engine_id
            self.context["rule_name"]=rule_engine.rule_name
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
            "function": node.function_name,
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
