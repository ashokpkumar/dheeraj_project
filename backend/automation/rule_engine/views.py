import json

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ClaimsData, RuleEdge, RuleEngine, RuleLogic, RuleList, RuleEngineProcessed
from .registry import get_all_functions
from .executor import GraphRuleExecutor as RuleExecutor
from .utils import topological_sort
from .serializers import RuleEngineSerializer, RuleListSerializer
# from ..scheduler import load_active_jobs
from rest_framework.decorators import api_view
from rest_framework.response import Response

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.utils.dateparse import parse_date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from rule_engine.models import RuleLogic, ParamModel


# backend/views.py
import csv
from datetime import datetime
from django.http import StreamingHttpResponse, HttpResponseBadRequest
from django.utils import timezone


# API 1: Discover Functions


@api_view(["GET"])
def dashboard(request):


    # ------------- helpers (all inside this function) -------------
    def parse_bool(val, default=False):
        if val is None:
            return default
        return str(val).lower() in ("true", "1", "yes", "y", "t")

    def parse_int(val, name):
        if val is None or val == "":
            return None
        try:
            return int(val)
        except ValueError:
            raise ValidationError({name: "Must be an integer"})

    def parse_comma_ints(val, name):
        if not val:
            return None
        try:
            return [int(x.strip()) for x in val.split(",") if x.strip()]
        except ValueError:
            raise ValidationError({name: "Comma-separated integers expected"})

    def get_timezone(tz_param):
        fallback = getattr(settings, "TIME_ZONE", "UTC")
        tz_name = tz_param or fallback or "UTC"
        try:
            return ZoneInfo(tz_name)
        except Exception:
            raise ValidationError({"tz": f"Unknown timezone '{tz_name}'. Use a valid IANA name (e.g., 'UTC', 'America/Chicago')."})

    def parse_dates(start_date_str, end_date_str, tz):
        start, end = None, None
        if start_date_str:
            d = parse_date(start_date_str)
            if not d:
                raise ValidationError({"start_date": "Expected YYYY-MM-DD"})
            start = datetime.combine(d, time.min).replace(tzinfo=tz)
        if end_date_str:
            d = parse_date(end_date_str)
            if not d:
                raise ValidationError({"end_date": "Expected YYYY-MM-DD"})
            end = datetime.combine(d, time.max).replace(tzinfo=tz)
        return start, end
    # --------------------------------------------------------------

    params = request.query_params
    tz = get_timezone(params.get("tz"))
    aggregate = parse_bool(params.get("aggregate"), default=False)

    # base queryset with eager load
    qs = RuleEngineProcessed.objects.all()

    # filters
    engine_ids = parse_comma_ints(params.get("rule_engine_id"), "rule_engine_id")
    min_claims = parse_int(params.get("min_claims"), "min_claims")
    max_claims = parse_int(params.get("max_claims"), "max_claims")
    sd, ed = parse_dates(params.get("start_date"), params.get("end_date"), tz)

    if engine_ids:
        qs = qs.filter(rule_engine_id__in=engine_ids)
    if sd:
        qs = qs.filter(processed_at__gte=sd)
    if ed:
        qs = qs.filter(processed_at__lte=ed)
    if min_claims is not None:
        qs = qs.filter(claims_count__gte=min_claims)
    if max_claims is not None:
        qs = qs.filter(claims_count__lte=max_claims)

    order = (params.get("order") or "asc").lower()
    ordering = "processed_at" if order == "asc" else "-processed_at"
    qs = qs.order_by(ordering, "id")

    if not aggregate:
        # ---------- list mode (manual dicts + DRF pagination) ----------
        paginator = PageNumberPagination()
        paginator.page_size = int(params.get("page_size") or 50)
        # cap to 500
        if paginator.page_size > 500:
            paginator.page_size = 500
        page = paginator.paginate_queryset(qs, request)

        data = [
            {
                "id": obj.id,
                "rule_engine": {
                    "id": obj.rule_engine_id,
                    "rule_name": obj.rule_name,
                },
                "processed_at": obj.processed_at,
                "claims_count": obj.claims_count,
            }
            for obj in page
        ]
        return paginator.get_paginated_response(data)

    # ---------- aggregate mode ----------
    group_by = (params.get("group_by") or "").lower()
    if group_by not in ("day", "week", "month"):
        raise ValidationError({"group_by": "Required when aggregate=true. Must be one of: day, week, month."})

    if group_by == "day":
        trunc = TruncDate("processed_at", tzinfo=tz)
    elif group_by == "week":
        trunc = TruncWeek("processed_at", tzinfo=tz)
    else:
        trunc = TruncMonth("processed_at", tzinfo=tz)

    values = ["period_start"]
    if engine_ids and len(engine_ids) > 1:
        values.append("rule_engine_id")

    agg_qs = (
        qs.annotate(period_start=trunc)
          .values(*values)
          .annotate(claims_count=Sum("claims_count"))
    )

    # ordering for aggregates
    if "rule_engine_id" in values:
        agg_qs = agg_qs.order_by("period_start" if order == "asc" else "-period_start", "rule_engine_id")
    else:
        agg_qs = agg_qs.order_by("period_start" if order == "asc" else "-period_start")

    results = []
    for row in agg_qs:
        item = {
            "period_start": row["period_start"],
            "claims_count": row["claims_count"],
        }
        if "rule_engine_id" in row:
            item["rule_engine_id"] = row["rule_engine_id"]
        results.append(item)

    return Response({
        "aggregate": True,
        "group_by": group_by,
        "timezone": str(tz),
        "results": results,
    })




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
    rule_id = request.data.get("rule_id")  # Present only in edit mode

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
    existing_rule = RuleEngine.objects.filter(rule_name=rule_name).first()
    if not  rule_id and existing_rule :
        return Response(
               f"Rule with name '{rule_name}' Already found",
                status=status.HTTP_400_BAD_REQUEST
                
            )
    # Add IDs to edges if missing
    for i, edge in enumerate(edges):
        if "id" not in edge:
            edge["id"] = f"edge-{i+1}"

    # -------- EDIT MODE: UPDATE EXISTING RULE IN-PLACE --------
    if rule_id:
        try:
            rule_engine = RuleEngine.objects.get(id=rule_id)
        except RuleEngine.DoesNotExist:
            return Response(
                {"error": f"Rule with id '{rule_id}' not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Update top-level fields on the existing record (id stays the same)
        rule_engine.rule_name = rule_name
        rule_engine.reactflow_json = {"nodes": nodes, "edges": edges}
        rule_engine.save()

        # Clear only the child nodes and edges — reporting rows keep their FK intact
        RuleEdge.objects.filter(rule_engine=rule_engine).delete()
        RuleList.objects.filter(rule_engine=rule_engine).delete()

    # -------- CREATE MODE: NEW RULE ENGINE --------
    else:
        rule_engine = RuleEngine.objects.create(
            rule_name=rule_name,
            reactflow_json={"nodes": nodes, "edges": edges}
        )

    # -------- REBUILD NODES --------
    node_instance_map = {}

    for index, node in enumerate(nodes):

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

    # -------- REBUILD EDGES --------
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
            "message": "Rule updated successfully" if rule_id else "Rule saved successfully",
            "rule_engine_id": rule_engine.id
        },
        status=status.HTTP_201_CREATED
    )

# API 3: Execute Rule (Debug)

@api_view(["POST"])
def execute_rule(request, rule_id):
    rule_engine = RuleEngine.objects.filter(id=rule_id).first()
    if not rule_engine:
        return Response(
            {"error": f"Rule with id '{rule_id}' not found"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    executor = RuleExecutor(rule_id,True)

    result = executor.execute()

    return Response(result)


# API 4: List Rules

@api_view(["GET"])
def list_rules(request):

    rules = RuleEngine.objects.filter(deleted=False).order_by("-created_at").all()

    # Return only id and rule_name
    rules_data = [
        {"id": rule.id, "rule_name": rule.rule_name}
        for rule in rules
    ]

    return Response(rules_data)


# API 5: Rule Details

@api_view(["GET","DELETE"])
def rule_details(request, rule_id):
    if request.method == "DELETE":
        try:
            rule = RuleEngine.objects.get(id=rule_id)
            rule.deleted = True
            rule.save()
            return Response(
                {"message": "Rule deleted successfully"},
                status=status.HTTP_200_OK
            )
        except RuleEngine.DoesNotExist:
            return Response(
                {"error": "Rule not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
    if request.method == "GET":
        rule = RuleEngine.objects.get(id=rule_id)

        steps = RuleList.objects.filter(
            rule_engine=rule
        )

        steps_serializer = RuleListSerializer(
            steps,
            many=True
        )

        # Ensure edges have IDs
        reactflow_json = rule.reactflow_json
        edges = reactflow_json.get("edges", [])
        for i, edge in enumerate(edges):
            if "id" not in edge:
                edge["id"] = f"edge-{i+1}"

        return Response({
            "rule_engine": rule.rule_name,
            "reactflow_json": reactflow_json,
            "steps": steps_serializer.data
        })



class Echo:
    """A minimal file-like wrapper that just returns the value."""
    def write(self, value):
        return value

def _parse_date(value: str | None):
    if not value:
        return None
    try:
        if len(value) == 10:
            # YYYY-MM-DD
            return datetime.strptime(value, "%Y-%m-%d")
        # ISO-like datetime string
        return datetime.fromisoformat(value)
    except ValueError:
        return None

def export_claims_csv(request):
    if request.method != "GET":
        return HttpResponseBadRequest("Only GET allowed.")

    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))
    rule_name = request.GET.get("rule_name")
    rule_engine_id = request.GET.get("rule_engine_id")
    qs = ClaimsData.objects.all().only(
        "claims_id", "processed_date", "rule_name", "manual", "status"
    )

    if rule_name:
        qs = qs.filter(rule_name__iexact=rule_name)
    if start:
        qs = qs.filter(processed_date__gte=start)
    if rule_engine_id:
        qs = qs.filter(rule_engine_id=rule_engine_id)

    headers = ["claims_id", "processed_date", "rule_name", "manual", "status"]
    pseudo_buffer = Echo()
    writer = csv.writer(pseudo_buffer)

    def row_iter():
        yield writer.writerow(headers)
        for row in qs.order_by("processed_date").iterator(chunk_size=2000):
            yield writer.writerow([
                row.claims_id,
                row.processed_date.isoformat() if row.processed_date else "",
                row.rule_name,
                "TRUE" if row.manual else "FALSE",
                row.status,
            ])

    filename = f"claims_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    resp = StreamingHttpResponse(row_iter(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp



from .models import ScheduledJob


# ─────────────────────────────────────────────
# GET  /scheduler/jobs/        → list all jobs
# POST /scheduler/jobs/        → create a job
# ─────────────────────────────────────────────

@api_view(["GET", "POST"])
def scheduled_jobs(request):

    if request.method == "GET":
        return _list_jobs(request)

    if request.method == "POST":
        return _create_job(request)

def _fetch_schedule(job):
    schedule = None
    if job.schedule_config.get("type") == "interval":
        schedule = f"Every {job.interval} {job.unit}"
    elif job.schedule_config.get("type") == "weekly":
        schedule = f"Every Week on {job.schedule_config.get('days', 'Monday')} at {job.schedule_config.get('time', '00:00')}"
    elif job.schedule_config.get("type") == "daily":
        schedule = f"Daily at {job.schedule_config.get('time', '00:00')}"
    elif job.schedule_config.get("type") == "once":
        schedule = f"Run Once at {job.schedule_config.get('date').split("T")[0] +\
                                   " " + job.schedule_config.get('date').split("T")[1]}"
    return schedule

def _list_jobs(request):
    jobs = ScheduledJob.objects.all()

    data = [
        {
            "id":         job.id,
            "rule_name":  job.rule_name,
            "rule_id":    job.rule_id,
            "interval":   job.interval,
            "unit":       job.unit,
            # "schedule":   _fetch_schedule(job),# human-readable
            "is_active":  job.is_active,
            "created_at": job.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": job.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "combinations": job.combinations,
            "schedule_config": job.schedule_config,
            "job_name": job.job_name,
        }
        for job in jobs
    ]

    return Response({
            "count":   len(data),
            "results": data,
        }, status=status.HTTP_200_OK)

def _create_job(request):
    #rule_name = request.data.get("rule_name", "").strip()
    rule_id  = int(request.data.get("rule_id"))
    interval  = request.data.get("interval")
    unit      = request.data.get("unit", "seconds")
    is_active = request.data.get("is_active", True)
    combinations = request.data.get("combinations", None)
    schedule_config = request.data.get("schedule_config", None)
    job_name = request.data.get("job_name", "").strip()
    # ── Validation ──────────────────────────────────────────────────────────
   
    if schedule_config.get("type") == "interval" and interval is None:
        return Response({"error": "interval is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        if interval:
            interval = int(interval)
            if interval <= 0:
                raise ValueError
    except (ValueError, TypeError):
        return Response({"error": "interval must be a positive integer"}, status=status.HTTP_400_BAD_REQUEST)

    if unit not in ("seconds", "minutes", "hours"):
        return Response({"error": "unit must be one of: seconds, minutes, hours"}, status=status.HTTP_400_BAD_REQUEST)

    # ── Upsert (update if rule_name exists, create if not) ──────────────────
    rule_name = RuleEngine.objects.filter(id=rule_id).values_list("rule_name", flat=True).first()
    job, created = ScheduledJob.objects.update_or_create(
        rule_name=rule_name,
        job_name = job_name,
        defaults={
            "rule_id":   rule_id,
            "interval":  interval,
            "unit":      unit,
            "is_active": is_active,
            "combinations": combinations,  # ← ADD THIS
            "schedule_config": schedule_config, 
        },
    )

    return Response({
            "message":   "Job created" if created else "Job updated",
            "id":        job.id,
            "rule_name": job.rule_name,
            "interval":  job.interval,
            "unit":      job.unit,
            "schedule":  f"every {job.interval} {job.unit}",
            "is_active": job.is_active,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ─────────────────────────────────────────────
# PATCH /scheduler/jobs/<id>/toggle/  → pause / resume
# DELETE /scheduler/jobs/<id>/        → remove a job
# ─────────────────────────────────────────────

@api_view(["PATCH"])
def toggle_job(request, job_id):
    try:
        job = ScheduledJob.objects.get(id=job_id)
    except ScheduledJob.DoesNotExist:
        return Response(
            {"error": f"Job {job_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    job.is_active = not job.is_active
    job.save(update_fields=["is_active", "updated_at"])
    # load_active_jobs()  # Sync changes to the scheduler immediately
    return Response({
            "message":   "Job resumed" if job.is_active else "Job paused",
            "id":        job.id,
            "rule_name": job.rule_name,
            "is_active": job.is_active,
        }, status=status.HTTP_200_OK)


@api_view(["DELETE"])
def delete_job(request, job_id):
    try:
        job = ScheduledJob.objects.get(id=job_id)
    except ScheduledJob.DoesNotExist:
        return Response({"error": f"Job {job_id} not found"}, status=status.HTTP_404_NOT_FOUND)

    rule_name = job.rule_name
    job.delete()

    return Response({"message": f"Job '{rule_name}' deleted"}, status=status.HTTP_200_OK)
