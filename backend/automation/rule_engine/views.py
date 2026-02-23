import json

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import RuleEdge, RuleEngine, RuleLogic, RuleList
from .registry import get_all_functions
from .executor import GraphRuleExecutor as RuleExecutor
from .utils import topological_sort
from .serializers import RuleEngineSerializer, RuleListSerializer

from rest_framework.decorators import api_view
from rest_framework.response import Response

from rule_engine.models import RuleLogic, ParamModel

# API 1: Discover Functions


@api_view(["GET"])
def discover_functions(request):

    functions = RuleLogic.objects.all()

    result = []

    for function in functions:

        inputs = _get_params(function.input_params)

        outputs = _get_params(function.output_params)

        result.append({
            "function_name": function.function_name,
            "inputs": inputs,
            "outputs": outputs
        })

    return Response(result)


def _get_params(parameter_group_id):

    if not parameter_group_id:
        return []

    params = ParamModel.objects.filter(
        parameter_group_id=parameter_group_id
    ).exclude(param_name="__group__")

    return [
        {
            "name": param.param_name,
            "type": param.param_type
        }
        for param in params
    ]


from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import RuleEngine, RuleList, RuleLogic, RuleEdge


@api_view(["POST"])
def save_rule(request):

    rule_name = request.data.get("rule_name")
    nodes = request.data.get("nodes")
    edges = request.data.get("edges")

    # -------- VALIDATION --------
    if not rule_name:
        return Response(
            {"error": "rule_name is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not nodes:
        return Response(
            {"error": "nodes are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if edges is None:
        return Response(
            {"error": "edges are required (can be empty list)"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # -------- CREATE RULE ENGINE --------
    rule_engine = RuleEngine.objects.create(
        rule_name=rule_name,
        reactflow_json={
            "nodes": nodes,
            "edges": edges
        }
    )

    # -------- CREATE NODES --------
    node_instance_map = {}

    for index,node in enumerate(nodes):

        node_id = node.get("id")
        data = node.get("data", {})

        function_name = data.get("function_name")
        params = data.get("params", {})

        if not function_name:
            return Response(
                {"error": f"function_name missing in node {node_id}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            rule_logic = RuleLogic.objects.get(
                function_name=function_name
            )
        except RuleLogic.DoesNotExist:
            return Response(
                {"error": f"Function '{function_name}' not registered"},
                status=status.HTTP_400_BAD_REQUEST
            )

        rule_node = RuleList.objects.create(
            rule_engine=rule_engine,
            rule_logic=rule_logic,
            rule_function_order=index,
            params=params
        )

        node_instance_map[node_id] = rule_node

    # -------- CREATE EDGES --------
    for edge in edges:

        source_id = edge.get("source")
        target_id = edge.get("target")
        condition = edge.get("condition")

        if source_id not in node_instance_map:
            return Response(
                {"error": f"Invalid source node: {source_id}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if target_id not in node_instance_map:
            return Response(
                {"error": f"Invalid target node: {target_id}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        RuleEdge.objects.create(
            rule_engine=rule_engine,
            source=node_instance_map[source_id],
            target=node_instance_map[target_id],
            condition=condition
        )

    return Response(
        {
            "message": "Rule saved successfully",
            "rule_engine_id": rule_engine.id
        },
        status=status.HTTP_201_CREATED
    )

# API 3: Execute Rule (Debug)

@api_view(["POST"])
def execute_rule(request, rule_id):

    executor = RuleExecutor(rule_id)

    result = executor.execute()

    return Response(result)


# API 4: List Rules

@api_view(["GET"])
def list_rules(request):

    rules = RuleEngine.objects.all()

    # Return only id and rule_name
    rules_data = [
        {"id": rule.id, "rule_name": rule.rule_name}
        for rule in rules
    ]

    return Response(rules_data)


# API 5: Rule Details

@api_view(["GET"])
def rule_details(request, rule_id):

    rule = RuleEngine.objects.get(id=rule_id)

    steps = RuleList.objects.filter(
        rule_engine=rule
    )

    steps_serializer = RuleListSerializer(
        steps,
        many=True
    )

    return Response({
        "rule_engine": rule.rule_name,
        "reactflow_json": rule.reactflow_json,
        "steps": steps_serializer.data
    })
