from rest_framework import serializers
from .models import RuleEngine, RuleList


class RuleEngineSerializer(serializers.ModelSerializer):

    class Meta:
        model = RuleEngine
        fields = "__all__"


class RuleListSerializer(serializers.ModelSerializer):

    class Meta:
        model = RuleList
        fields = [
            "id",
            "rule_function_order",
            "function_name",
            "params"
        ]
