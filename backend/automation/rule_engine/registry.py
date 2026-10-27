import logging
import threading

from django.db import models, transaction

from rule_engine.models import RuleLogic, ParamModel


logger = logging.getLogger(__name__)

FUNCTION_REGISTRY = {}

_REGISTRATION_LOCK = threading.Lock()


class FunctionMeta:

    def __init__(self, func, name, inputs=None, outputs=None, tag=None, color=None):

        self.func = func
        self.name = name
        self.inputs = inputs or []
        self.outputs = outputs or []
        self.tag = tag
        self.color = color


def register_function(name=None, inputs=None, outputs=None, tag=None, color=None):

    def decorator(func):

        function_name = name or func.__name__

        input_params = inputs or []
        output_params = outputs or []

        with _REGISTRATION_LOCK:

            # Register in memory only. DB sync happens later, once the app
            # registry and database connection are ready (see
            # rule_engine.registry.sync_registry_to_db), so this stays safe
            # to run during app loading.
            FUNCTION_REGISTRY[function_name] = FunctionMeta(
                func=func,
                name=function_name,
                inputs=input_params,
                outputs=output_params,
                tag=tag,
                color=color,
            )

        return func

    return decorator


def sync_registry_to_db():
    """Persist all in-memory registered functions to the database.

    Must only be called once the database is reachable (e.g. from
    RuleEngineConfig.ready(), after app loading has finished). Errors are
    logged per-function so a single bad function doesn't block the rest or
    fail silently.
    """

    for meta in FUNCTION_REGISTRY.values():

        try:
            _register_function_in_db(
                meta.name,
                meta.inputs,
                meta.outputs,
                tag=meta.tag,
                color=meta.color,
            )
        except Exception:
            logger.exception(
                "Failed to sync function '%s' to the database", meta.name
            )


def _register_function_in_db(function_name, inputs, outputs, tag=None, color=None):

    with transaction.atomic():

        input_group_id = _create_param_group(
            function_name,
            inputs,
            "input"
        )

        output_group_id = _create_param_group(
            function_name,
            outputs,
            "output"
        )

        defaults = {
            "input_params": input_group_id,
            "output_params": output_group_id,
        }
        if tag is not None:
            defaults["tag"] = tag
        if color is not None:
            defaults["color"] = color

        RuleLogic.objects.update_or_create(
            function_name=function_name,
            defaults=defaults,
        )

def _create_param_group(function_name, params, group_type):

    if not params:
        return None

    group_key = f"{function_name}_{group_type}"

    existing = ParamModel.objects.filter(
        param_name="__group__",
        param_type=group_key
    ).first()

    if existing:
        group_id = existing.parameter_group_id
    else:
        max_group = ParamModel.objects.aggregate(
            max_group=models.Max("parameter_group_id")
        )["max_group"]

        group_id = (max_group or 0) + 1

        ParamModel.objects.create(
            parameter_group_id=group_id,
            param_name="__group__",
            param_type=group_key
        )

    # normalize params
    normalized_params = []

    for param in params:

        if isinstance(param, str):

            normalized_params.append({
                "name": param,
                "type": "string",
                "options": None
            })

        elif isinstance(param, dict):

            normalized_params.append({
                "name": param["name"],
                "type": param.get("type", "string"),
                "options": param.get("options", None),
                "default": param.get("default", None),
            })

        else:
            raise Exception(
                f"Invalid param format in {function_name}: {param}"
            )

    # upsert params so re-registration picks up new options
    for param in normalized_params:

        ParamModel.objects.update_or_create(
            parameter_group_id=group_id,
            param_name=param["name"],
            defaults={
                "param_type": param["type"],
                "param_options": param["options"],
                "param_default": param.get("default"),
            }
        )

    # remove params that are no longer in the definition
    current_names = {p["name"] for p in normalized_params}
    ParamModel.objects.filter(
        parameter_group_id=group_id,
    ).exclude(
        param_name__in=current_names,
    ).exclude(
        param_name="__group__",
    ).delete()

    return group_id



def get_all_functions():

    return FUNCTION_REGISTRY


def get_function(name):

    meta = FUNCTION_REGISTRY.get(name)

    if not meta:
        raise Exception(f"{name} not registered")

    return meta.func
