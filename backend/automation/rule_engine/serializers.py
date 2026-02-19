from rest_framework import serializers
from .models import RuleEngine, RuleList


class RuleEngineSerializer(serializers.ModelSerializer):

    class Meta:
        model = RuleEngine
        fields = "__all__"


class RuleListSerializer(serializers.ModelSerializer):

    function_name = serializers.CharField(
        source="rule_logic.function_name"
    )

    class Meta:
        model = RuleList
        fields = [
            "id",
            "rule_function_order",
            "function_name",
            "params"
        ]
