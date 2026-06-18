# Distributed Rules Engine & Automation Platform

A visual no-code workflow automation system for processing insurance claims at scale. It combines a React-based graph UI with a Django backend, Celery distributed task queue, and Windows emulator automation for legacy system (EXTRA/Attachmate) integration.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [How It Works (Logical Blocks)](#how-it-works-logical-blocks)
  - [Frontend — Visual Workflow Builder](#frontend--visual-workflow-builder)
  - [Backend — Django REST API](#backend--django-rest-api)
  - [Rule Executor (Graph Engine)](#rule-executor-graph-engine)
  - [Function Registry](#function-registry)
  - [Business Logic Functions](#business-logic-functions)
  - [Celery Task Queue](#celery-task-queue)
  - [Scheduler](#scheduler)
  - [Emulator Agent](#emulator-agent)
  - [Database Layer](#database-layer)
- [API Endpoints Reference](#api-endpoints-reference)
- [Data Flow Walkthrough](#data-flow-walkthrough)
- [Running the Project](#running-the-project)
  - [Prerequisites](#prerequisites)
  - [Backend Setup (Docker)](#backend-setup-docker)
  - [Frontend Setup (Local Dev)](#frontend-setup-local-dev)
  - [Building and Distributing the Docker Image](#building-and-distributing-the-docker-image)
- [Environment Variables](#environment-variables)
- [Troubleshooting Guide](#troubleshooting-guide)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│   Vite + React 19 + @xyflow/react (visual graph editor)        │
│   localhost:5173 (dev) / localhost:3000 (prod)                 │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API (HTTP)
┌────────────────────────────▼────────────────────────────────────┐
│                     DJANGO API (Port 8000)                      │
│   Views → Serializers → Executor → Registry → Functions        │
└────┬──────────────────────────────────────────┬────────────────┘
     │ Celery tasks                              │ DB queries
┌────▼────────────────────────┐    ┌────────────▼───────────────┐
│     REDIS (Port 6379)       │    │       MSSQL Databases       │
│  Broker + Result Backend    │    │  Default: Automation rules  │
│  + Emulator claim registry  │    │  External: Claims inventory │
└────┬────────────────────────┘    └────────────────────────────┘
     │
┌────▼────────────────────────────────────────────────────────────┐
│              CELERY WORKER + CELERY BEAT                        │
│  Workers execute tasks; Beat manages scheduled job dispatch     │
└────┬────────────────────────────────────────────────────────────┘
     │ HTTP / Win32 COM
┌────▼────────────────────────────────────────────────────────────┐
│         EMULATOR AGENT (Flask, Windows-native)                  │
│  Manages pool of 16 EXTRA emulator sessions for screen scraping │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
dheeraj_project/
├── backend/
│   └── automation/
│       ├── automation/                  # Django project configuration
│       │   ├── settings.py             # DB, Celery, CORS, middleware config
│       │   ├── urls.py                 # Root URL routing
│       │   ├── celery.py               # Celery app + beat schedule
│       │   ├── wsgi.py                 # WSGI entrypoint
│       │   └── dbrouters.py            # Routes MSSQL models to external DB
│       ├── rule_engine/                # Core app — all business logic
│       │   ├── models.py               # All DB models
│       │   ├── views.py                # REST API views
│       │   ├── urls.py                 # App-level URL routes
│       │   ├── serializers.py          # DRF serializers
│       │   ├── executor.py             # Graph execution engine
│       │   ├── tasks.py                # Celery tasks
│       │   ├── registry.py             # Function registration + discovery
│       │   ├── utils.py                # Topological sort helper
│       │   └── functions/
│       │       ├── validation.py       # Claim validation functions
│       │       ├── claims.py           # Claim extraction/export functions
│       │       ├── db_function.py      # Database read/write functions
│       │       └── helpers.py          # Windows emulator screen helpers
│       ├── emulator_agent/
│       │   └── agent.py                # Flask app — emulator pool manager
│       ├── scheduler.py                # Legacy thread-based scheduler
│       ├── requirements.txt            # Python dependencies
│       ├── Dockerfile                  # Container image build
│       ├── docker-compose.yml          # Service orchestration
│       ├── .env                        # Runtime secrets (git-ignored)
│       └── .env.example                # Template for .env
├── UI/
│   └── my-react-flow-app/
│       ├── src/
│       │   ├── App.jsx                 # Root component, all state + tabs
│       │   ├── api/api.jsx             # All backend API calls
│       │   └── components/
│       │       ├── RuleNode.jsx        # Custom graph node component
│       │       ├── ProcessingPage.jsx  # Dashboard + CSV export
│       │       └── SchedulerPage.jsx   # Scheduled job management
│       ├── package.json
│       └── vite.config.js
├── build_and_save.ps1                  # Build Docker image + save to tar
├── split_image.ps1                     # Split tar into chunks (file size limits)
├── join_chunks.ps1                     # Reassemble chunks into tar
├── load_image.ps1                      # docker load from tar
└── load_image_rancher.ps1              # Load into Rancher environment
```

---

## How It Works (Logical Blocks)

### Frontend — Visual Workflow Builder

**File:** [UI/my-react-flow-app/src/App.jsx](UI/my-react-flow-app/src/App.jsx)

The UI is a single-page application with three tabs:

| Tab | Component | Purpose |
|-----|-----------|---------|
| Workflow | App.jsx (inline) | Create, edit, visualize, and execute rule graphs |
| Scheduler | SchedulerPage.jsx | Create/manage scheduled job runs |
| Processing | ProcessingPage.jsx | View execution history, export CSVs |

**Workflow Editor — what happens:**
1. On load → calls `GET /rule_engine/functions/` to fetch all registered functions and their parameter schemas
2. User drags/adds functions as nodes onto the canvas (powered by `@xyflow/react`)
3. User connects nodes with edges; edges can carry Python conditions (e.g., `len(valid_claims) > 0`)
4. User clicks **Save Workflow** → calls `POST /rule_engine/rules/save/` with the full graph JSON
5. User clicks **Execute Flow** → calls `POST /rule_engine/rules/<id>/execute/`

**Edit Mode:** On entering edit mode, the current `nodes` + `edges` are backed up in state. Cancel restores the backup. Save sends the updated graph with the existing `rule_id` so the backend updates rather than creates.

**API client:** [UI/my-react-flow-app/src/api/api.jsx](UI/my-react-flow-app/src/api/api.jsx) — all `fetch()` calls to `http://localhost:8000`.

---

### Backend — Django REST API

**File:** [backend/automation/rule_engine/views.py](backend/automation/rule_engine/views.py)

All endpoints are under the `/rule_engine/` prefix (see [backend/automation/rule_engine/urls.py](backend/automation/rule_engine/urls.py)).

Key view functions:

| Function | Route | What it does |
|----------|-------|-------------|
| `discover_functions` | `GET /functions/` | Returns all @register_function entries with I/O param schemas |
| `save_rule` | `POST /rules/save/` | Creates or updates a RuleEngine + associated RuleList/RuleEdge records |
| `execute_rule` | `POST /rules/<id>/execute/` | Instantiates GraphRuleExecutor and runs it synchronously |
| `list_rules` | `GET /rules/` | Returns non-deleted rules list |
| `rule_details` | `GET/DELETE /rules/<id>/` | Returns full graph JSON or soft-deletes the rule |
| `dashboard` | `GET /dashboard/` | Aggregated or list view of execution records with date filters |
| `export_claims_csv` | `GET /claims/export/` | Streaming chunked CSV download |
| `scheduled_jobs` | `GET/POST /scheduler/jobs/` | List or create scheduled jobs |
| `toggle_job` | `PATCH /scheduler/jobs/<id>/toggle/` | Pause/resume a scheduled job |
| `delete_job` | `DELETE /scheduler/jobs/<id>/` | Remove a scheduled job |

---

### Rule Executor (Graph Engine)

**File:** [backend/automation/rule_engine/executor.py](backend/automation/rule_engine/executor.py)

**Class:** `GraphRuleExecutor`

This is the core of the system. It turns a saved workflow (nodes + edges) into an ordered sequence of function calls.

```
GraphRuleExecutor(rule_engine_id, manual=True)
    └── execute()
          ├── if manual=True  → _execute_workflow() in-process (synchronous)
          └── if manual=False → _execute_workflow() in a subprocess (isolated)

_execute_workflow()
    1. Load RuleList nodes from DB (ordered by rule_function_order)
    2. Load RuleEdge edges from DB
    3. Build adjacency list: {source_id → [(target_id, condition), ...]}
    4. Find start nodes: nodes with no incoming edges
    5. BFS traversal:
       a. Execute current node's function via registry.get_function(name)
       b. Store output in shared `context` dict
       c. For each outgoing edge: evaluate edge.condition against context
       d. If condition passes (or is null): enqueue target node
    6. Return execution log
```

**Edge conditions** are Python expressions stored as strings and evaluated via `ast.literal_eval` or `eval`. Example: `len(valid_claims) > 0` — if the upstream function returned an empty list, this edge is not traversed.

---

### Function Registry

**File:** [backend/automation/rule_engine/registry.py](backend/automation/rule_engine/registry.py)

Functions are registered using the `@register_function` decorator. At module import time, the decorator:
1. Stores the callable in `FUNCTION_REGISTRY` (in-memory dict)
2. Reads the function's type annotations to extract parameter names/types
3. Creates or updates `RuleLogic` + `ParamModel` DB records so the UI can discover the function

```python
# Example usage
@register_function
def validate_required_fields(claims: list, required_fields: list) -> list:
    ...
```

`get_function(name)` retrieves the callable at execution time.

---

### Business Logic Functions

**Directory:** [backend/automation/rule_engine/functions/](backend/automation/rule_engine/functions/)

All functions marked with `@register_function` are automatically discoverable by the UI and executable as nodes in a workflow.

---

#### validation.py — [View file](backend/automation/rule_engine/functions/validation.py)

Pure data transformation functions; no DB or network calls. Safe to use anywhere in a workflow.

| Function | Description |
|----------|-------------|
| `validate_required_fields(claims, required_fields)` | Checks every claim dict for the presence and non-null value of each field in `required_fields`. Returns two lists: `valid_claims` (all fields present) and `invalid_claims` (with a `_validation_error` key showing which fields are missing). |
| `validate_claim_amount_range(claims, min_amount, max_amount)` | Filters claims by checking whether their `amount` field falls within `[min_amount, max_amount]`. Claims outside that range are moved to `invalid_claims` with `_validation_error: "Amount out of range"`. |
| `deduplicate_claims(claims, unique_field)` | Scans the claim list and keeps the first occurrence of each value in `unique_field`; subsequent duplicates go to `duplicate_claims`. Uses a `set` for O(n) deduplication. |
| `filter_claims_by_status(claims, allowed_status)` | Keeps only claims whose `status` field is in `allowed_status` (a list). All non-matching claims are silently dropped; result returned as `filtered_claims`. |
| `calculate_claim_tax(claims, tax_rate)` | Multiplies each claim's `amount` by `tax_rate` and stores the result as a `tax` key on the claim dict. Returns the enriched list as `claims_with_tax`. |
| `auto_approve_claims(claims, approval_threshold)` | Claims at or below `approval_threshold` get `status = "approved"` and go to `approved_claims`; all others get `status = "manual_review"` and go to `manual_review_claims`. |
| `merge_claim_lists(claims_a, claims_b)` | Concatenates two claim lists with Python `+` and returns the combined result as `merged_claims`. Useful for rejoining branches in a workflow after a split. |
| `test_dummy_jb()` | Empty placeholder function with no inputs or outputs. Used to verify the `@register_function` decorator and DB registration are working without side effects. |

---

#### claims.py — [View file](backend/automation/rule_engine/functions/claims.py)

Functions that interact with the Windows Automation Service for emulator-based data extraction.

| Function | Description |
|----------|-------------|
| `scrap_claims_from_emulator()` | Reads `claim_ids` from the workflow context, forwards them to the Windows Automation Service (Flask API), and receives structured claim field data scraped from EXTRA terminal screens. Raises a clear exception if the Windows service is unreachable, rather than silently returning empty. |
| `convert_claims_data_to_csv(output_path)` | Reads `scrapped_claims` from the workflow context and writes them to a CSV file at `output_path` using pandas. Returns `{"status": True}` on success or `{"status": False}` on failure, with error details logged. |

---

#### db_function.py — [View file](backend/automation/rule_engine/functions/db_function.py)

Functions that read from the external MSSQL claims inventory and write results back to the automation database.

| Function | Description |
|----------|-------------|
| `fetch_claim_ids_from_db(rules)` | Queries `TBL_DAILY_INVENTORY_NEW` (external MSSQL) for `MCRFM_ROLL_CD` values whose `MACRO_RULE` matches any entry in the `rules` list. Returns up to 100 distinct claim IDs as `claim_ids`, which downstream nodes (e.g. `scrap_claims_from_emulator`) consume from context. |
| `add_scrapped_values_to_db(rule_name)` | Reads `scrapped_claims` from context, creates a `RuleEngineProcessed` record summarising the run (rule name, timestamp, claim count), then bulk-inserts each claim into `ClaimsData` via `bulk_upsert_claims`. This is typically the final node in a processing workflow. |

---

#### helpers.py — [View file](backend/automation/rule_engine/functions/helpers.py)

Low-level Win32 COM helpers for EXTRA emulator automation. **Windows-only** — requires `pywin32`. Not registered as workflow functions; called internally by the Windows Automation Service.

| Function | Description |
|----------|-------------|
| `bulk_upsert_claims(data_list, rule_name, manual, rule_engine_id)` | Bulk-inserts a list of scraped claim dicts into `ClaimsData` inside a single DB transaction, batched at 1000 rows. Maps `CLAIM CONTROL #` → `claims_id` and `MACRO STATUS` → `status`. |
| `wait_for_screen(screen, timeout=15)` | Polls `screen.OIA.Xstatus` every 100 ms until the emulator host signals ready (`Xstatus == 0`) or the timeout is exceeded. Called after every key send to prevent race conditions. |
| `get_screen_id(screen)` | Reads characters at row 1, col 2 (10 chars) to identify which EXTRA screen is currently displayed (e.g. `"CPS850.01"`). Used by `process_claim` to drive the navigation state machine. |
| `send_enter(screen)` | Sends the `<ENTER>` key to the emulator and waits for the host to settle. Wrapper used throughout to ensure reliable navigation. |
| `send_pf(screen, n)` | Sends program-function key `<PFn>` (e.g. PF9 to enter claim lookup mode) and waits for the screen to be ready. |
| `send_erase_eof(screen)` | Clears the field from the cursor to end-of-field with `<EraseEOF>`, then waits for the host. Called before typing new values to avoid appending to existing content. |
| `place_value(screen, val, r, c)` | Moves cursor to `(row, col)`, clears to end-of-field, and types `val`. No-ops silently if `val` is `None` or empty, keeping callers clean. |
| `clean_name(nm)` | Normalises whitespace in a name string by splitting on spaces and rejoining with a single space. Used to tidy member names scraped from the terminal. |
| `rtn_patient_seq_no(screen, seq_no)` | Searches the patient listing screen for a matching sequence number, paging forward with PF11 until found or the screen wraps back to the start. Returns the row number if found, or `0` if not. |
| `read_cps850_fields(screen)` | Reads ~45 labelled fields from the CPS850.01 enrollment/member screen (employee name, SSN, cert, plan, effective dates, provider address, etc.) and returns them as a flat dict. |
| `read_blx2460_fields(screen)` | Extracts 3 fields (`UB/HCFA AFV FIELD`, `UB/HCFA CONDITION NOTE`, `UB TOB`) from the BLX2460.01 UB claim screen. |
| `read_cps450_fields(screen)` | Reads 5 fields including HCFA approval code and CFV field from the CPS450.01 claim adjudication screen. |
| `read_cps310_fields(screen)` | Reads provider name, address, city, state, and ZIP from the CPS310.01 provider record screen. |
| `process_claim(screen, claim_id, method, cert_date_mmddyy, seq_no, dental_flag)` | Drives a full multi-screen navigation workflow for a single claim ID through CPS520, CPS850, BLX2460, CPS450, CPS310, and others. Returns a dict of all captured fields plus a `MACRO STATUS` (e.g. `"DONE.Released"`). This is the core screen-scraping orchestrator. |
| `attach_emulator_sessions(n=4)` | Connects to up to `n` already-open EXTRA emulator sessions using Win32 COM (`EXTRA.System`) and returns them as a list. Initialises COM for the calling thread via `pythoncom.CoInitialize()`. |

---

### Celery Task Queue

**Files:**
- [backend/automation/automation/celery.py](backend/automation/automation/celery.py) — App config + beat schedule
- [backend/automation/rule_engine/tasks.py](backend/automation/rule_engine/tasks.py) — Task definitions

| Task | Type | Behavior |
|------|------|---------|
| `execute_rule_engine` | `shared_task`, max_retries=3 | Async wrapper around `GraphRuleExecutor`; retries with backoff |
| `execute_scheduled_job` | `shared_task` | Validates job is active, calls `execute_rule_engine.delay()` |
| `sync_scheduled_jobs` | `shared_task` | Runs every 5 min (orchestrator only); reads DB and rebuilds Celery Beat schedule |

**Celery Beat** is the clock process that reads `sync_scheduled_jobs` output and enqueues tasks at the right times. Only runs when `IS_ORCHESTRATOR=True` in `.env`.

---

### Scheduler

**Files:**
- [backend/automation/scheduler.py](backend/automation/scheduler.py) — Legacy standalone scheduler
- `sync_scheduled_jobs` task in `tasks.py` — Active Celery Beat-based scheduler

The **Celery Beat** scheduler (`sync_scheduled_jobs`) is the primary mechanism. It supports:
- `interval`: Every N seconds/minutes/hours
- `daily`: At a specific time each day (e.g., `10:00`)
- `weekly`: On specific days at a specific time
- `once`: Single one-time execution at a given date+time
- `combinations`: Multiple intervals combined (e.g., run at both 5-minute and 10-minute intervals)

`scheduler.py` is the legacy alternative that uses the `schedule` library in a background daemon thread — kept for reference but Celery Beat is preferred.

---

### Emulator Agent

**File:** [backend/automation/emulator_agent/agent.py](backend/automation/emulator_agent/agent.py)

A Flask REST API that runs **natively on Windows** (outside Docker) and manages a shared pool of 16 EXTRA terminal emulator sessions.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/emulators/claim` | POST | Worker requests N emulator slots on startup |
| `/emulators/release/{id}` | POST | Worker returns slots on shutdown |
| `/emulators/heartbeat/{id}` | POST | Renews TTL to prevent expiration of claimed slots |
| `/emulators/status` | GET | Shows which slots are claimed/available |
| `/emulators/scrape` | POST | Trigger claim data extraction via emulator |
| `/health` | GET | Health check |

Claims are stored in Redis with TTL-based expiration so stale claims are automatically cleaned up if a worker dies.

When `docker compose up --scale worker=4` is run:
- Worker 1 claims emulators 1–4
- Worker 2 claims emulators 5–8
- Worker 3 claims emulators 9–12
- Worker 4 claims emulators 13–16

---

### Database Layer

**File:** [backend/automation/rule_engine/models.py](backend/automation/rule_engine/models.py)

**Two databases:**
- `default` — automation app data (rule definitions, execution history)
- `mssql` — external read-only claims inventory (`TBL_DAILY_INVENTORY_NEW`)

Router: [backend/automation/automation/dbrouters.py](backend/automation/automation/dbrouters.py) — routes `DailyInventory` model queries to the `mssql` connection.

| Model | Table | Purpose |
|-------|-------|---------|
| `RuleEngine` | `rule_engine` | Workflow definitions (stores full React Flow JSON) |
| `RuleList` | `rule_list` | Ordered execution nodes per workflow |
| `RuleEdge` | `rule_edge` | Directed edges with optional Python condition |
| `RuleLogic` | `rule_logic` | Function metadata (name, input/output param groups) |
| `ParamModel` | `param_model` | Parameter definitions (name, type) per function |
| `ClaimsData` | `claims_data` | Per-execution log (claims_id, status, rule_name, date) |
| `RuleEngineProcessed` | `rule_engine_processed` | Aggregated metrics per rule run (claims count) |
| `ScheduledJob` | `scheduled_job` | Scheduled execution configurations |
| `DailyInventory` | `TBL_DAILY_INVENTORY_NEW` | Read-only external claims inventory (130+ fields) |

`DailyInventory` is protected by a `ReadOnlyModel` base class that raises `PermissionDenied` on any save/delete attempt.

---

## API Endpoints Reference

Base URL: `http://localhost:8000`

```
GET    /rule_engine/functions/                     List all registered functions + param schemas
POST   /rule_engine/rules/save/                    Save (create or update) a workflow
GET    /rule_engine/rules/                         List all non-deleted workflows
GET    /rule_engine/rules/<id>/                    Get full workflow JSON
DELETE /rule_engine/rules/<id>/                    Soft-delete a workflow
POST   /rule_engine/rules/<id>/execute/            Execute a workflow manually
GET    /rule_engine/dashboard/                     Execution history (list or aggregated)
GET    /rule_engine/claims/export/                 Stream claims CSV
GET    /rule_engine/scheduler/jobs/                List scheduled jobs
POST   /rule_engine/scheduler/jobs/                Create/update a scheduled job
PATCH  /rule_engine/scheduler/jobs/<id>/toggle/   Toggle job active/inactive
DELETE /rule_engine/scheduler/jobs/<id>/           Delete a scheduled job
```

---

## Data Flow Walkthrough

### Creating and Running a Workflow

```
1. Browser → GET /rule_engine/functions/
   ↓ Returns function list with input/output param metadata

2. User builds graph in UI (nodes + edges)

3. Browser → POST /rule_engine/rules/save/
   Body: { rule_name, nodes: [...], edges: [...] }
   ↓ Backend: creates RuleEngine, rebuilds RuleList, rebuilds RuleEdge

4. Browser → POST /rule_engine/rules/<id>/execute/
   ↓ Backend: GraphRuleExecutor._execute_workflow()
      a. Topological sort of nodes
      b. BFS: call each function, pass results in context dict
      c. Evaluate edge conditions, traverse only passing edges
      d. Log results to ClaimsData + RuleEngineProcessed

5. Browser → GET /rule_engine/dashboard/
   ↓ Returns execution records and aggregated metrics
```

### Full Claims Processing Pipeline (Scheduled)

```
Celery Beat → sync_scheduled_jobs (every 5 min)
  ↓ Reads ScheduledJob table, rebuilds schedule

At scheduled time → execute_scheduled_job.delay(job_id)
  ↓ Validates job is active
  ↓ execute_rule_engine.delay(rule_id)

Celery Worker → GraphRuleExecutor
  1. fetch_claim_ids_from_db
     → Queries TBL_DAILY_INVENTORY_NEW for MACRO_RULE matches
     → Returns list of claim IDs

  2. scrap_claims_from_emulator
     → Calls Windows Emulator Agent /emulators/scrape
     → Agent uses EXTRA Win32 COM to navigate screens
     → Extracts claim fields from terminal screens
     → Returns structured claim data

  3. validate_required_fields / auto_approve_claims / etc.
     → Business logic on claim data

  4. add_scrapped_values_to_db
     → Writes to ClaimsData (per-claim log)
     → Writes to RuleEngineProcessed (aggregate count)

Dashboard now shows updated results.
```

---

## Running the Project

### Prerequisites

- Docker Desktop (Windows)
- Node.js 18+ and npm
- PowerShell (for image build scripts)
- Access to the MSSQL external claims database (for full pipeline)
- EXTRA terminal emulator installed on Windows host (for emulator automation)

---

### Backend Setup (Docker)

**1. Configure environment variables**

```powershell
cd backend\automation
copy .env.example .env
# Edit .env with your actual DB credentials, secret key, etc.
```

Key values to set in `.env`:

```env
SECRET_KEY=your-django-secret-key
DEBUG=False
IS_ORCHESTRATOR=True          # Set True only on the machine running Celery Beat
DB_HOST=automation_mssql      # MSSQL container hostname
DB_USER=sa
DB_PASSWORD=YourPassword
EXTERNAL_DB_HOST=...          # External MSSQL for claims inventory
```

**2. Start all services**

```powershell
cd backend\automation
docker compose up -d
```

This starts four containers:
- `automation_redis` — Redis broker
- `automation_api` — Django API on port 8000
- `automation_celery_worker` — Celery worker
- `automation_celery_beat` — Celery Beat (scheduler)

**3. Scale workers (optional)**

```powershell
docker compose up --scale worker=4
```

**4. Run database migrations**

```powershell
docker compose exec api python manage.py migrate
```

**5. Verify the backend is running**

Open `http://localhost:8000/rule_engine/functions/` — should return a JSON list of functions.

**6. View Celery task monitor (optional)**

Flower is available at `http://localhost:5555` (credentials: `admin` / `password` — see `.env`).

---

### Frontend Setup (Local Dev)

**1. Install dependencies**

```powershell
cd UI\my-react-flow-app
npm install
```

**2. Start the dev server**

```powershell
npm run dev
```

The UI is available at `http://localhost:5173`.

**3. Build for production**

```powershell
npm run build
```

Output goes to `dist/` and can be served via nginx or any static file server.

> The React app talks to `http://localhost:8000` directly. If you change the backend port, update the base URL in [UI/my-react-flow-app/src/api/api.jsx](UI/my-react-flow-app/src/api/api.jsx).

---

### Building and Distributing the Docker Image

Use these scripts when you need to transfer the Docker image to an air-gapped or offline environment.

**Step 1 — Build image and save to tar**

```powershell
powershell -ExecutionPolicy Bypass -File .\build_and_save.ps1
```

Builds `os_image:latest` and saves it as `os_image.tar`.

**Step 2 — Split into chunks (for file size limits)**

```powershell
powershell -ExecutionPolicy Bypass -File .\split_image.ps1
```

Splits `os_image.tar` into smaller chunks.

**Step 3 — Transfer chunks to target machine**

Copy the chunk files to the target environment.

**Step 4 — Reassemble on the target machine**

```powershell
Unblock-File .\join_chunks.ps1
powershell -ExecutionPolicy Bypass -File .\join_chunks.ps1
```

**Step 5 — Load the image into Docker**

```powershell
powershell -ExecutionPolicy Bypass -File .\load_image.ps1
# OR directly:
docker load -i os_image.tar
```

**Step 6 — Load into Rancher (if applicable)**

```powershell
Unblock-File .\load_image_rancher.ps1
powershell -ExecutionPolicy Bypass -File .\load_image_rancher.ps1
```

---

## Environment Variables

Full list from [backend/automation/.env.example](backend/automation/.env.example):

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | Django secret key (required) |
| `DEBUG` | `False` | Django debug mode |
| `ALLOWED_HOSTS` | `*` | Comma-separated allowed hostnames |
| `IS_ORCHESTRATOR` | `True` | Enable Celery Beat scheduler |
| `CELERY_BROKER_URL` | `redis://automation_redis:6379/0` | Redis URL for task queue |
| `CELERY_RESULT_BACKEND` | `redis://automation_redis:6379/0` | Redis URL for task results |
| `REDIS_URL` | `redis://automation_redis:6379/0` | Redis URL for emulator registry |
| `DB_HOST` | `automation_mssql` | Default MSSQL host |
| `DB_NAME` | — | Default database name |
| `DB_USER` | `sa` | Default DB user |
| `DB_PASSWORD` | — | Default DB password |
| `EXTERNAL_DB_HOST` | — | External claims inventory MSSQL host |
| `EXTERNAL_DB_NAME` | `MACRO_IT_PROJECT` | External DB name |
| `EXTERNAL_DB_USE_WINDOWS_AUTH` | `False` | Use Windows auth for external DB |
| `FLOWER_PORT` | `5555` | Celery Flower monitoring port |
| `FLOWER_BASIC_AUTH` | `admin:password` | Flower HTTP basic auth |
| `WORKERS` | `4` | Gunicorn worker count |
| `WORKER_TIMEOUT` | `60` | Gunicorn worker timeout (seconds) |

---

## Troubleshooting Guide

### Backend Issues

**Problem: API returns 500 on all requests**
- Where to look: Django logs via `docker compose logs api`
- Common causes: `.env` not configured, DB connection failure, migration not run
- Fix: Run `docker compose exec api python manage.py migrate`; check DB credentials in `.env`

**Problem: Functions not showing up in the UI (`/functions/` returns empty)**
- Where to look: [backend/automation/rule_engine/registry.py](backend/automation/rule_engine/registry.py) and [backend/automation/rule_engine/functions/](backend/automation/rule_engine/functions/)
- The functions must be imported at startup for `@register_function` to fire
- Check: [backend/automation/rule_engine/apps.py](backend/automation/rule_engine/apps.py) — `ready()` must import the functions module
- Check: DB has `RuleLogic` + `ParamModel` rows populated

**Problem: Rule execution hangs or times out**
- Where to look: [backend/automation/rule_engine/executor.py](backend/automation/rule_engine/executor.py) — `_execute_workflow()`
- The executor runs in a subprocess when `manual=False`. Check if the subprocess is spawning correctly
- Check: `docker compose logs celery-worker` for task errors and tracebacks

**Problem: Celery tasks not being consumed**
- Where to look: [backend/automation/automation/celery.py](backend/automation/automation/celery.py)
- Run: `docker compose logs celery-worker`
- Verify Redis is up: `docker compose exec api redis-cli -h automation_redis ping`
- Verify `CELERY_BROKER_URL` in `.env` matches the Redis container hostname

**Problem: Scheduled jobs not firing**
- Where to look: [backend/automation/rule_engine/tasks.py](backend/automation/rule_engine/tasks.py) — `sync_scheduled_jobs`
- Verify `IS_ORCHESTRATOR=True` in `.env`
- Verify Celery Beat is running: `docker compose logs celery-beat`
- Check the ScheduledJob records in Django admin (`/admin/`) — `is_active` must be `True`
- `sync_scheduled_jobs` runs every 5 minutes; wait one cycle after creating a new job

**Problem: MSSQL external DB connection refused**
- Where to look: [backend/automation/automation/settings.py](backend/automation/automation/settings.py) — `DATABASES['mssql']`
- Check `EXTERNAL_DB_HOST`, `EXTERNAL_DB_NAME`, credentials in `.env`
- If using Windows auth (`EXTERNAL_DB_USE_WINDOWS_AUTH=True`), the container must be joined to the domain
- Test connectivity: `docker compose exec api python -c "import pyodbc; print(pyodbc.connect('...'))"` 

**Problem: `DailyInventory` model raising PermissionDenied**
- This is expected — the model is intentionally read-only
- Where to look: [backend/automation/rule_engine/models.py](backend/automation/rule_engine/models.py) — `ReadOnlyModel` base class
- Never call `.save()` or `.delete()` on `DailyInventory` instances

---

### Frontend Issues

**Problem: UI shows blank page / no functions in palette**
- Check browser console for network errors
- Verify the backend is running at `http://localhost:8000`
- Check CORS settings in [backend/automation/automation/settings.py](backend/automation/automation/settings.py) — `CORS_ALLOWED_ORIGINS` must include your dev server port (5173 or 3000)

**Problem: "Save Workflow" returns 400**
- Where to look: [backend/automation/rule_engine/views.py](backend/automation/rule_engine/views.py) — `save_rule`
- The request body must include `rule_name`, `nodes` (array), and `edges` (array)
- Each node must have `id`, `data.label` (function name), and optionally `data.params`
- The function name in each node must exist in the `FUNCTION_REGISTRY`

**Problem: Graph editor nodes not connecting**
- This is a React Flow UI issue — check browser console for `@xyflow/react` errors
- Ensure handles are properly defined in [UI/my-react-flow-app/src/components/RuleNode.jsx](UI/my-react-flow-app/src/components/RuleNode.jsx)

---

### Emulator Agent Issues

**Problem: `scrap_claims_from_emulator` fails**
- The emulator agent must be running **on the Windows host** (not inside Docker)
- Start the Flask agent: `python backend/automation/emulator_agent/agent.py`
- Verify EXTRA emulator sessions are open and logged in
- Check `pywin32` is installed: `pip install pywin32`
- Where to look: [backend/automation/rule_engine/functions/helpers.py](backend/automation/rule_engine/functions/helpers.py) for screen navigation logic

**Problem: Workers can't claim emulators**
- Check the emulator agent is reachable from inside Docker (host network or explicit IP)
- Check Redis is up for the claim registry TTL store
- Run `GET /emulators/status` to see which slots are taken

---

### Docker / Infrastructure Issues

**Problem: `docker compose up` fails with port conflict**
- Port 8000 (API), 6379 (Redis), 5555 (Flower) must be free
- Run `netstat -aon | findstr ":8000"` on Windows to identify conflicting processes

**Problem: `os_image:latest` not found when building**
- The custom base image must be loaded first: `docker load -i os_image.tar`
- Build the base image using: `powershell -ExecutionPolicy Bypass -File .\build_and_save.ps1`

**Problem: Container exits immediately after start**
- Check entrypoint: `docker compose logs api`
- The entrypoint script at `/entrypoint.sh` inside the container selects the service mode
- Verify the `Dockerfile` at [backend/automation/Dockerfile](backend/automation/Dockerfile) is using the correct entrypoint

---

### Adding a New Function

1. Create or edit a file in [backend/automation/rule_engine/functions/](backend/automation/rule_engine/functions/)
2. Add the `@register_function` decorator:
   ```python
   from rule_engine.registry import register_function

   @register_function
   def my_new_function(claims: list, threshold: float) -> list:
       # your logic here
       return filtered_claims
   ```
3. Import the function in the app's `ready()` method so the decorator fires on startup
4. Restart the API container — the function appears in the UI automatically
5. Use type annotations — they are parsed to generate the parameter schema shown in the UI
