from django.db import models
from django.core.exceptions import PermissionDenied


class ParamModel(models.Model):

    id = models.AutoField(primary_key=True)

    parameter_group_id = models.IntegerField()

    param_name = models.CharField(max_length=255)

    param_type = models.CharField(max_length=50)

    class Meta:
        db_table = "param_model"

# models.py

class RuleEdge(models.Model):

    rule_engine = models.ForeignKey(
        "RuleEngine",
        on_delete=models.CASCADE,
        related_name="edges"
    )

    source = models.ForeignKey(
        "RuleList",
        on_delete=models.CASCADE,
        related_name="outgoing_edges"
    )

    target = models.ForeignKey(
        "RuleList",
        on_delete=models.CASCADE,
        related_name="incoming_edges"
    )

    condition = models.CharField(
        max_length=255,
        null=True,
        blank=True
    )
    """
    condition examples:
    None → always execute
    approved == True
    len(valid_claims) > 0
    context["fraud_score"] < 50
    """



class RuleLogic(models.Model):

    id = models.AutoField(primary_key=True)

    function_name = models.CharField(max_length=255)

    input_params = models.IntegerField(null=True,blank=True)

    output_params = models.IntegerField(null=True,blank=True)

    class Meta:
        db_table = "rule_logic"

class ClaimsData(models.Model):
    id =  models.AutoField(primary_key=True)
    claims_id = models.CharField(max_length=255)
    processed_date = models.DateTimeField(auto_now_add=True)
    rule_name = models.CharField(max_length=255)
    manual = models.BooleanField()
    status = models.CharField(max_length=255)
    rule_engine_id =  models.CharField(max_length=255)

    class Meta:
        db_table = "claims_data"

class RuleEngine(models.Model):

    id = models.AutoField(primary_key=True)
  
    rule_name = models.CharField(max_length=255, null=True,blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted = models.BooleanField(default=False)
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

    rule_engine_id = models.IntegerField(null=True,blank=True)
    rule_name = models.CharField(max_length=255, null=True,blank=True)
    processed_at = models.DateTimeField()
    claims_count = models.IntegerField()
    class Meta:
        db_table = "rule_engine_processed"


class ReadOnlyModel(models.Model):
    """Prevents any accidental writes to the MSSQL database."""
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        raise PermissionDenied("MSSQL Model: Read-only")

    def delete(self, *args, **kwargs):
        raise PermissionDenied("MSSQL Model: Read-only")


class DailyInventory(ReadOnlyModel):
    use_mssql = True  # Tells the router to use the MSSQL DB

    ID = models.IntegerField(primary_key=True)
    RULE_ID_NBR = models.CharField(max_length=50, db_column="RULE-ID-NBR", null=True)
    MACRO_RULE = models.CharField(max_length=255, null=True)
    RULE_TYPE = models.CharField(max_length=50, db_column="RULE-TYPE", null=True)
    RULE_REGN = models.CharField(max_length=50, db_column="RULE-REGN", null=True)
    RULE_NAME = models.CharField(max_length=255, db_column="RULE-NAME", null=True)
    MCRFM_ROLL_CD = models.CharField(max_length=50, db_column="MCRFM-ROLL-CD", null=True)

    # Example of how to map date fields
    ACTV_DT = models.DateField(db_column="ACTV-DT", null=True)
    SERV_RCVD_DT = models.DateField(db_column="SERV-RCVD-DT", null=True)
    SERV_CMPL_DT = models.DateField(db_column="SERV-CMPL-DT", null=True)

    # Example numeric
    CHRG_AMT = models.DecimalField(max_digits=12, decimal_places=2, db_column="CHRG-AMT", null=True)
    PMT_AMT = models.DecimalField(max_digits=12, decimal_places=2, db_column="PMT-AMT", null=True)

    # Add more fields gradually — you don’t need all 130 right away.
    # Django will ignore missing columns when reading (but not writing).
    # You can safely add only what you intend to use.

    class Meta:
        managed = False
        db_table = "TBL_DAILY_INVENTORY_NEW"




from django.db import models


class ScheduleUnit(models.TextChoices):
    SECONDS = "seconds", "Seconds"
    MINUTES = "minutes", "Minutes"
    HOURS   = "hours",   "Hours"


class ScheduledJob(models.Model):
    """
    One row = one scheduled task that maps to a named RuleEngine rule.
    The scheduler process reads this table every minute and syncs jobs live.
    """
    rule_id      = models.IntegerField(null=True, blank=True,
        help_text="Must match RuleEngine.id exactly"    )
    rule_name   = models.CharField(
        max_length=255,
        unique=True,
        help_text="Must match RuleEngine.rule_name exactly"
    )
    interval    = models.PositiveIntegerField(
        help_text="How often to run (numeric value)"
    )
    unit        = models.CharField(
        max_length=10,
        choices=ScheduleUnit.choices,
        default=ScheduleUnit.SECONDS,
        help_text="Unit for the interval"
    )
    is_active   = models.BooleanField(
        default=True,
        help_text="Uncheck to pause without deleting"
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["rule_name"]
        verbose_name        = "Scheduled Job"
        verbose_name_plural = "Scheduled Jobs"

    def __str__(self):
        status = "active" if self.is_active else "paused"
        return f"{self.rule_name} — every {self.interval} {self.unit} ({status})"
