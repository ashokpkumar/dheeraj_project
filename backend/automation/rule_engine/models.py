from django.db import models


class ParamModel(models.Model):

    id = models.AutoField(primary_key=True)

    parameter_group_id = models.IntegerField()

    param_name = models.CharField(max_length=255)

    param_type = models.CharField(max_length=50)

    class Meta:
        db_table = "param_model"


class RuleLogic(models.Model):

    id = models.AutoField(primary_key=True)

    function_name = models.CharField(max_length=255)

    input_params = models.IntegerField()

    output_params = models.IntegerField()

    class Meta:
        db_table = "rule_logic"


class RuleEngine(models.Model):

    id = models.AutoField(primary_key=True)

    rule_name = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    # Optional but strongly recommended if column exists
    reactflow_json = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "rule_engine"


class RuleList(models.Model):

    id = models.AutoField(primary_key=True)

    rule_engine = models.ForeignKey(
        RuleEngine,
        on_delete=models.CASCADE,
        db_column="rule_engine_id"
    )

    rule_logic = models.ForeignKey(
        RuleLogic,
        on_delete=models.CASCADE,
        db_column="rule_logic_id"
    )

    rule_function_order = models.IntegerField()

    # stores node params
    params = models.JSONField(default=dict)

    class Meta:
        db_table = "rule_list"
        ordering = ["rule_function_order"]


class RuleEngineProcessed(models.Model):

    id = models.AutoField(primary_key=True)

    rule_engine = models.ForeignKey(
        RuleEngine,
        on_delete=models.CASCADE,
        db_column="rule_engine_id"
    )

    processed_at = models.DateTimeField()

    class Meta:
        db_table = "rule_engine_processed"
