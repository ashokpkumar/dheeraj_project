# app_logging

Standalone, standard-library-only file logging for the backend. One structured
record per event, written as **CSV (default)** or a **flat key=value file**,
with columns that line up with Azure Application Insights so the files can be
shipped there later.

## Switching format / settings

Set in `backend/automation/.env` (or the process environment). No code change.

| Variable | Default | Meaning |
|---|---|---|
| `APP_LOG_FORMAT` | `csv` | `csv` or `flat` |
| `APP_LOG_DIR` | `backend/automation/logs` | Output folder (relative paths resolve against `backend/automation`) |
| `APP_LOG_LEVEL` | `INFO` | `DEBUG` `INFO` `WARNING` `ERROR` `CRITICAL` |
| `APP_LOG_APP_NAME` | `umr-claims-automation` | Written to `app_name` (Azure `cloud_RoleName`); also the file-name prefix |
| `APP_LOG_ENVIRONMENT` | `development` | `development` / `test` / `production` |
| `APP_LOG_APP_VERSION` | `unknown` | Release version |
| `APP_LOG_MAX_BYTES` | `52428800` | Start a new file past this size (`0` = never) |
| `APP_LOG_RETENTION_DAYS` | `30` | Delete older files (`0` = keep forever) |
| `APP_LOG_CONSOLE` | `true` | Also print a short line to the console |
| `APP_LOG_SKIP_PATHS` | `/static/,/assets/,/favicon.ico` | Request paths the middleware does not log |
| `APP_LOG_HTTP_BODIES` | `true` | Log API request / response parameters and bodies |
| `APP_LOG_MAX_BODY_CHARS` | `8000` | Truncate each logged payload to this length |
| `APP_LOG_REDACT_KEYS` | (empty) | Extra comma-separated key names to mask, on top of the built-in list |

Files: a **new file is started every day** - `<app>-<YYYY-MM-DD>.csv` (or `.log`
for flat), then `<app>-<date>.1.csv` ... if one day's file passes the size limit.
Dates are UTC (midnight UTC rolls the file). Safe for several
processes (Waitress, executor child processes, scheduler) writing at once.

## Usage

```python
from app_logging import get_logger, log_context, timed

logger = get_logger(__name__)          # logger name -> `module` column

logger.info("Claims exported", extra={"event_name": "claims_export",
                                      "result_code": 200, "rows": 120})

with log_context(rule_engine_id=5, rule_name="Nightly"):   # stamped on every record inside
    with timed(logger, "node", node_id=12, node_function="validate"):
        run()          # logs node_completed / node_failed with duration_ms + success
```

* `extra={...}` keys that match a column fill that column; **any other key is
  collected into `custom_dimensions`** (JSON).
* `logger.exception(...)` fills `exception_type`, `exception_message`, `stack_trace`.
* **Every API call logs its request and response parameters** (one record per
  call, in `request_query`, `request_body`, `response_body` plus sizes). Keys
  containing `password`, `token`, `secret`, `authorization`, `api_key`,
  `cookie`, `session`, ... are masked as `***REDACTED***` at any depth. File
  uploads log only field names and file name/size/type; streaming responses
  (e.g. the claims CSV export) and binary bodies log a placeholder. Bodies
  over 1 MB are not logged. Disable with `APP_LOG_HTTP_BODIES=false`.
* Business events are logged in the views (rule save / delete / execute, job
  create / pause / delete, export, function refresh), the function registry,
  app start-up, the executor (workflow, every node, bad edge conditions,
  unregistered functions), claim saves, the emulator automation, the
  scheduler and server start-up. Validation failures are logged as WARNING.
* The `RequestLoggingMiddleware` (registered first in `MIDDLEWARE`) logs every
  HTTP request with method, URL, `result_code`, `duration_ms`, client IP, user
  agent and returns an `X-Request-ID` header. It reuses an incoming W3C
  `traceparent` / `X-Request-ID` as `operation_id`.
* The rule executor logs `workflow_started`, `workflow_completed|failed` and
  `node_completed|failed` per node; the scheduler logs its job runs. The
  `operation_id` is carried into the executor's child process.

## Columns

| Column | Azure App Insights field | Notes |
|---|---|---|
| `timestamp` | `timestamp` | ISO-8601 UTC, ms |
| `level` | - | DEBUG / INFO / WARNING / ERROR / CRITICAL |
| `severity_level` | `severityLevel` | 0 Verbose, 1 Info, 2 Warning, 3 Error, 4 Critical |
| `app_name` | `cloud_RoleName` | |
| `environment` | (custom dimension) | |
| `app_version` | `application_Version` | |
| `host` | `cloud_RoleInstance` | machine name |
| `process_id`, `thread_name` | (custom dimension) | |
| `module` | (custom dimension) | logger name, e.g. `rule_engine.executor` |
| `function`, `source_file`, `line_no` | (custom dimension) | code location |
| `operation_id` | `operation_Id` | correlates all records of one request / run |
| `parent_id` | `operation_ParentId` | from `traceparent` when present |
| `operation_name` | `operation_Name` | e.g. `POST rules/<int:rule_id>/execute/` |
| `user_id`, `session_id` | `user_Id`, `session_Id` | |
| `rule_engine_id`, `rule_name`, `node_id`, `node_function` | (custom dimension) | rule engine context |
| `event_name` | (`name` for custom events) | stable machine-readable id |
| `message` | `message` | |
| `http_method`, `url` | `url` | |
| `request_query`, `request_body`, `request_size` | (custom dimension) | API request parameters / body (masked, truncated) |
| `response_body`, `response_size` | (custom dimension) | API response body (masked, truncated) |
| `result_code` | `resultCode` | HTTP status or your own code |
| `success` | `success` | derived from `result_code < 400` / level when not set |
| `duration_ms` | `duration` | |
| `client_ip`, `user_agent` | `client_IP` | |
| `exception_type`, `exception_message`, `stack_trace` | `type`, `outerMessage`, `details` | |
| `custom_dimensions` | `customDimensions` | JSON of every extra field |

`app_logging.AZURE_FIELD_MAP` holds the column -> Azure name mapping for a future exporter.

## Moving to Azure later

The columns already follow App Insights naming, so you can either rename them
with `AZURE_FIELD_MAP` and ingest the files, or add a second handler (for
example OpenTelemetry's `AzureMonitorLogExporter`) next to `app_file` in
`build_logging_config()`. Application code does not change.

## Tests

```
cd backend/automation
python -m unittest app_logging.tests -v
```
