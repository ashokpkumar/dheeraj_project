from collections import deque
import inspect
import multiprocessing
from multiprocessing import Process, Queue
import django
import os

from app_logging import get_logger, get_context, log_context, new_operation_id, timed

logger = get_logger(__name__)


def _execute_in_separate_process_worker(rule_engine_id, queue, operation_id=None):
    """Worker function to execute the workflow in a separate process with Django setup"""
    try:
        # Setup Django in the child process FIRST
        django.setup()
        
        # Import models AFTER django.setup()
        from .models import RuleEngine, RuleList, RuleEdge
        
        # Contextvars do not cross process boundaries; re-bind the parent's id
        # so child-process records correlate with the triggering request/job.
        with log_context(operation_id=operation_id):
            executor = GraphRuleExecutor(rule_engine_id, manual=False)
            result = executor._execute_workflow()
        queue.put(result)
    except Exception as e:
        logger.exception(
            "Rule execution failed in child process: %s", e,
            extra={"event_name": "workflow_failed", "rule_engine_id": rule_engine_id},
        )
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
            operation_id = get_context().get("operation_id") or new_operation_id()
            process = Process(
                target=_execute_in_separate_process_worker,
                args=(self.rule_engine_id, queue, operation_id),
            )
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
        if not get_context().get("operation_id"):
            with log_context(operation_id=new_operation_id()):
                return self._run_workflow()
        return self._run_workflow()

    def _run_workflow(self):
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

        with log_context(rule_engine_id=self.rule_engine_id):
            return self._run_queue(queue, adj)

    def _run_queue(self, queue, adj):
        manual = bool(self.context.get("manual"))
        logger.info("Workflow started", extra={"event_name": "workflow_started", "manual": manual})
        with timed(logger, "workflow", "Workflow finished", manual=manual):
            self._drain(queue, adj)
        return self.execution_log

    def _drain(self, queue, adj):
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
        
        try:
            function = get_function(node.function_name)
        except Exception:
            logger.exception("Function %r is not registered (node %s)", node.function_name, node.id,
                             extra={"event_name": "function_not_registered", "node_id": node.id,
                                    "node_function": node.function_name})
            raise
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

        with log_context(node_id=node.id, node_function=node.function_name,
                         rule_name=self.context.get("rule_name")):
            with timed(logger, "node", f"Node {node.id} ({node.function_name}) finished"):
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
            outcome = eval(condition, {}, self.context)
            logger.debug("Edge condition %r evaluated to %r", condition, outcome,
                         extra={"event_name": "edge_condition_evaluated"})
            return outcome
        except Exception as exc:
            logger.warning("Edge condition %r could not be evaluated (%s); treating as False",
                           condition, exc,
                           extra={"event_name": "edge_condition_error", "success": False})
            return False
