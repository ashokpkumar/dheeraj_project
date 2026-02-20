import json

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import RuleEngine, RuleLogic, RuleList
from .registry import get_all_functions
from .executor import RuleExecutor
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



# API 2: Save ReactFlow JSON as Rule

@api_view(["POST"])
def save_rule(request):

    rule_name = request.data["rule_name"]

    reactflow_json = request.data["reactflow_json"]

    nodes = reactflow_json["nodes"]
    edges = reactflow_json["edges"]

    order = topological_sort(nodes, edges)

    rule_engine = RuleEngine.objects.create(
        rule_name=rule_name,
        reactflow_json=reactflow_json
    )

    node_map = {
        node["id"]: node
        for node in nodes
    }

    for index, node_id in enumerate(order):

        node = node_map[node_id]

        function_name = node["data"]["function_name"]

        params = node["data"].get("params", {})

        rule_logic = RuleLogic.objects.get(
            function_name=function_name
        )

        RuleList.objects.create(
            rule_engine=rule_engine,
            rule_logic=rule_logic,
            rule_function_order=index,
            params=params
        )

    return Response({
        "rule_engine_id": rule_engine.id
    })


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
