from collections import deque
import inspect
import logging
import multiprocessing
from multiprocessing import Process, Queue
import django
import os

logger = logging.getLogger(__name__)


def _execute_in_separate_process_worker(rule_engine_id, queue):
    """Worker function to execute the workflow in a separate process with Django setup"""
    try:
        logger.debug(f"[Worker Process] Starting for RuleEngine {rule_engine_id}")
        
        # Setup Django in the child process FIRST
        django.setup()
        logger.debug(f"[Worker Process] Django setup completed")
        
        # Import models AFTER django.setup()
        from .models import RuleEngine, RuleList, RuleEdge
        
        executor = GraphRuleExecutor(rule_engine_id, manual=False)
        logger.debug(f"[Worker Process] Executor created for RuleEngine {rule_engine_id}")
        
        result = executor._execute_workflow()
        logger.debug(f"[Worker Process] Workflow execution completed, returning result")
        queue.put(result)
        
    except Exception as e:
        logger.error(f"[Worker Process] Error in separate process: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        queue.put([])


class GraphRuleExecutor:

    def __init__(self, rule_engine_id, manual):
        self.rule_engine_id = rule_engine_id
        self.context = {"manual": manual}
        self.execution_log = []
        logger.debug(f"GraphRuleExecutor initialized - RuleEngine: {rule_engine_id}, Manual: {manual}")

    def execute(self):
        """Execute the workflow with appropriate process handling"""
        try:
            logger.info(f"Starting execution of RuleEngine {self.rule_engine_id}")
            
            if not self.context.get("manual"):
                logger.debug(f"Running in separate process (automated mode)")
                # Run in separate process for automated execution
                queue = Queue()
                process = Process(
                    target=_execute_in_separate_process_worker, 
                    args=(self.rule_engine_id, queue)
                )
                logger.debug(f"Starting worker process for RuleEngine {self.rule_engine_id}")
                process.start()
                process.join()  # Wait for process to complete
                logger.debug(f"Worker process completed for RuleEngine {self.rule_engine_id}")
                
                if not queue.empty():
                    self.execution_log = queue.get()
                    logger.debug(f"Received {len(self.execution_log)} log entries from worker process")
                else:
                    logger.warning(f"No results received from worker process for RuleEngine {self.rule_engine_id}")
                
                return self.execution_log
            else:
                logger.debug(f"Running in current process (manual mode)")
                # Run in current process for manual execution
                return self._execute_workflow()
                
        except Exception as e:
            logger.error(f"Error during execution of RuleEngine {self.rule_engine_id}: {e}", exc_info=True)
            raise

    def _execute_workflow(self):
        """The actual execution logic that can run in current or separate process"""
        try:
            logger.info(f"Starting workflow execution for RuleEngine {self.rule_engine_id}")
            from .models import RuleEngine, RuleList, RuleEdge
            
            logger.debug(f"Fetching nodes for RuleEngine {self.rule_engine_id}")
            nodes = {
                node.id: node
                for node in RuleList.objects.filter(
                    rule_engine_id=self.rule_engine_id
                )
            }
            logger.debug(f"Found {len(nodes)} nodes for RuleEngine {self.rule_engine_id}")

            logger.debug(f"Fetching edges for RuleEngine {self.rule_engine_id}")
            edges = RuleEdge.objects.filter(
                rule_engine_id=self.rule_engine_id
            )
            edges_list = list(edges)
            logger.debug(f"Found {len(edges_list)} edges for RuleEngine {self.rule_engine_id}")

            # Build adjacency list
            adj = {}
            incoming = set()

            for edge in edges_list:
                adj.setdefault(edge.source_id, []).append(edge)
                incoming.add(edge.target_id)

            # Start nodes = no incoming edges
            start_nodes = [
                node for node_id, node in nodes.items()
                if node_id not in incoming
            ]
            logger.info(f"Found {len(start_nodes)} start nodes for RuleEngine {self.rule_engine_id}")

            queue = deque(start_nodes)
            executed_nodes = 0

            while queue:
                node = queue.popleft()
                logger.debug(f"Processing node {node.id} ({node.function_name})")

                result = self.execute_node(node)
                executed_nodes += 1

                for edge in adj.get(node.id, []):
                    condition_result = self.evaluate_condition(edge.condition)
                    logger.debug(f"Edge from node {node.id} to {edge.target_id}: condition={edge.condition}, result={condition_result}")
                    
                    if condition_result:
                        logger.debug(f"Condition met, adding target node {edge.target_id} to queue")
                        queue.append(edge.target)
                    else:
                        logger.debug(f"Condition not met, skipping target node {edge.target_id}")

            logger.info(f"Workflow execution completed for RuleEngine {self.rule_engine_id}. Executed {executed_nodes} nodes")
            return self.execution_log
            
        except Exception as e:
            logger.error(f"Error in workflow execution for RuleEngine {self.rule_engine_id}: {e}", exc_info=True)
            raise

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
