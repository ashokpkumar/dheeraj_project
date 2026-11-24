"""Column schema and record -> row conversion.

The columns deliberately mirror Azure Application Insights telemetry
(``traces`` / ``requests`` / ``exceptions`` tables) so the files can later be
shipped to Azure Monitor with a simple column rename - or with none at all
via the ``AZURE_FIELD_MAP`` below.

Anything passed in ``extra={...}`` that is not a column goes into the
``custom_dimensions`` JSON column (App Insights ``customDimensions``).
"""
from __future__ import annotations

import json
import logging
import socket
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List

from .config import LogConfig
from .context import get_context

# Azure Application Insights severityLevel
SEVERITY_NUMBER = {
    "DEBUG": 0,       # Verbose
    "INFO": 1,        # Information
    "WARNING": 2,     # Warning
    "ERROR": 3,       # Error
    "CRITICAL": 4,    # Critical
}

# Ordered output columns.
COLUMNS: List[str] = [
    # -- when / how bad
    "timestamp",            # ISO-8601 UTC, ms precision           -> timestamp
    "level",                # DEBUG/INFO/WARNING/ERROR/CRITICAL
    "severity_level",       # 0-4 (App Insights scale)             -> severityLevel
    # -- who emitted it
    "app_name",             #                                      -> cloud_RoleName
    "environment",
    "app_version",          #                                      -> application_Version
    "host",                 # machine name                         -> cloud_RoleInstance
    "process_id",
    "thread_name",
    "module",               # logger name, e.g. rule_engine.executor
    "function",
    "source_file",
    "line_no",
    # -- correlation
    "operation_id",         # one id per request / rule run        -> operation_Id
    "parent_id",            #                                      -> operation_ParentId
    "operation_name",       # e.g. "POST rules/<id>/execute/"      -> operation_Name
    "user_id",              #                                      -> user_Id
    "session_id",           #                                      -> session_Id
    # -- rule engine specifics
    "rule_engine_id",
    "rule_name",
    "node_id",
    "node_function",
    # -- what happened
    "event_name",           # short stable id, e.g. http_request, node_completed
    "message",              #                                      -> message
    # -- request / result
    "http_method",
    "url",                  #                                      -> url
    "result_code",          # HTTP status or custom code           -> resultCode
    "success",              # true / false                         -> success
    "duration_ms",          #                                      -> duration
    "client_ip",            #                                      -> client_IP
    "user_agent",
    # -- API payloads (sensitive keys masked, long values truncated)
    "request_query",        # URL query parameters (JSON)
    "request_body",         # request body / form fields (JSON or text)
    "request_size",         # bytes
    "response_body",        # response body (JSON or text)
    "response_size",        # bytes
    # -- errors
    "exception_type",       #                                      -> type
    "exception_message",
    "stack_trace",          #                                      -> details
    # -- everything else
    "custom_dimensions",    # JSON object                          -> customDimensions
]

# column -> Azure Application Insights field name (documentation + helper for
# a future exporter).
AZURE_FIELD_MAP: Dict[str, str] = {
    "timestamp": "timestamp",
    "severity_level": "severityLevel",
    "app_name": "cloud_RoleName",
    "app_version": "application_Version",
    "host": "cloud_RoleInstance",
    "operation_id": "operation_Id",
    "parent_id": "operation_ParentId",
    "operation_name": "operation_Name",
    "user_id": "user_Id",
    "session_id": "session_Id",
    "message": "message",
    "url": "url",
    "result_code": "resultCode",
    "success": "success",
    "duration_ms": "duration",
    "client_ip": "client_IP",
    "exception_type": "type",
    "stack_trace": "details",
    "custom_dimensions": "customDimensions",
}

# Columns a caller may supply through ``extra=`` or ``log_context``.
_CALLER_COLUMNS = {
    "operation_id", "parent_id", "operation_name", "user_id", "session_id",
    "rule_engine_id", "rule_name", "node_id", "node_function", "event_name",
    "http_method", "url", "result_code", "success", "duration_ms",
    "client_ip", "user_agent", "request_query", "request_body", "request_size",
    "response_body", "response_size",
}

# Attributes every LogRecord has - anything else was passed via ``extra``.
_STANDARD_RECORD_ATTRS = set(
    logging.LogRecord("x", logging.INFO, "x", 0, "x", None, None).__dict__
) | {"message", "asctime", "taskName"}

# Excel caps a cell at 32,767 characters.
MAX_FIELD_CHARS = 30000

_HOST = socket.gethostname()


def _truncate(value: str) -> str:
    if len(value) > MAX_FIELD_CHARS:
        return value[:MAX_FIELD_CHARS] + "...[truncated]"
    return value


def _format_timestamp(created: float) -> str:
    dt = datetime.fromtimestamp(created, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _derive_success(result_code: Any, level_no: int) -> Any:
    try:
        return int(result_code) < 400
    except (TypeError, ValueError):
        pass
    return False if level_no >= logging.ERROR else None


def build_row(record: logging.LogRecord, config: LogConfig) -> Dict[str, str]:
    """Convert a ``LogRecord`` into ``{column: string}`` for every column."""
    ctx = get_context()
    row: Dict[str, Any] = {col: "" for col in COLUMNS}

    row["timestamp"] = _format_timestamp(record.created)
    row["level"] = record.levelname
    row["severity_level"] = SEVERITY_NUMBER.get(record.levelname, 1)
    row["app_name"] = config.app_name
    row["environment"] = config.environment
    row["app_version"] = config.app_version
    row["host"] = _HOST
    row["process_id"] = record.process
    row["thread_name"] = record.threadName
    row["module"] = record.name
    row["function"] = record.funcName
    row["source_file"] = record.pathname.replace("\\", "/").rsplit("/", 1)[-1]
    row["line_no"] = record.lineno
    row["message"] = _truncate(record.getMessage())

    custom: Dict[str, Any] = {}

    # Context first, then per-call ``extra`` wins.
    for source in (ctx, {k: v for k, v in record.__dict__.items()
                         if k not in _STANDARD_RECORD_ATTRS}):
        for key, value in source.items():
            if key == "custom_dimensions" and isinstance(value, dict):
                custom.update(value)
            elif key in _CALLER_COLUMNS:
                if value is not None:
                    row[key] = value
            elif key not in COLUMNS:
                custom[key] = value

    if row["success"] in ("", None):
        row["success"] = _derive_success(row["result_code"], record.levelno)

    if record.exc_info and record.exc_info[0] is not None:
        exc_type, exc, tb = record.exc_info
        row["exception_type"] = exc_type.__name__
        row["exception_message"] = _truncate(str(exc))
        row["stack_trace"] = _truncate("".join(traceback.format_exception(exc_type, exc, tb)))
    elif record.stack_info:
        row["stack_trace"] = _truncate(record.stack_info)

    if custom:
        row["custom_dimensions"] = json.dumps(
            custom, default=str, ensure_ascii=False, sort_keys=True
        )

    return {col: _stringify(row[col]) for col in COLUMNS}
