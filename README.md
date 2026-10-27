# Rule Engine & Claims Automation

A visual **rule engine** for claims-processing automation. You build a workflow in a
drag-and-drop UI by chaining Python **functions** into a graph, save it as a named rule, and
run it on demand or on a schedule.

Most of those functions are **Python ports of legacy Excel/VBA macros**. Those macros drive
the **CPS mainframe** through an **Attachmate/Micro Focus EXTRA! (Reflection)** terminal
emulator to release, pend, split and update insurance claims. The original VBA source sits
next to each port, so you can compare the two line by line.


---

## Contents

- [How it works](#how-it-works)
- [Repository layout](#repository-layout)
- [The rule engine](#the-rule-engine)
- [Converted macros](#converted-macros)
- [Other built-in functions](#other-built-in-functions)
- [Prerequisites](#prerequisites)
- [Setup and running](#setup-and-running)
- [Building and running a rule](#building-and-running-a-rule)
- [Adding a function or porting a macro](#adding-a-function-or-porting-a-macro)
- [Troubleshooting and gotchas](#troubleshooting-and-gotchas)

---

## How it works

```
 ┌──────────────────────────┐   /rule_engine/*   ┌──────────────────────────────┐
 │ UI  (React + React Flow) │ ─────────────────▶ │ Django + DRF  (rule_engine)  │
 │ UI/my-react-flow-app     │  (Vite proxy →     │  • function registry         │
 │ build / save / run rules │   localhost:8000)  │  • rule graph storage        │
 └──────────────────────────┘                    │  • GraphRuleExecutor         │
                                                 └───────┬──────────────┬───────┘
          scheduler.py (separate process) ───────────────┤              │
          runs ScheduledJob rows on intervals            ▼              ▼
                                               ┌──────────────┐  ┌──────────────────────┐
                                               │ SQL Server   │  │ Registered functions │
                                               │ (rules, jobs,│  │ (macro ports)        │
                                               │  results,    │  │  ├─ EXTRA! emulator  │
                                               │  inventory)  │  │  │   (pywin32 COM)   │
                                               └──────────────┘  │  ├─ WebClaims / PDFs │
                                                                 │  └─ Excel / CSV I/O  │
                                                                 └──────────────────────┘
```

1. **Functions** are ordinary Python functions decorated with `@register_function`. When
   Django starts, every function is loaded into an in-memory registry. The UI's *Refresh
   functions* action syncs that registry to the database so the UI can list each function with
   its inputs and outputs.
2. A **rule** is a directed graph of function nodes. You build it in the UI and store it in the
   `RuleEngine`, `RuleList` and `RuleEdge` tables.
3. When a rule runs, `GraphRuleExecutor` walks the graph. Each function's return dict is merged
   into a shared **context**, and later nodes read their inputs from that context. That's how a
   "fetch claims" node passes its `df` to a "run macro" node.

---

## Repository layout

```
README.md                         ← this file
UI/my-react-flow-app/             ← React 19 + Vite + @xyflow/react front end
  src/App.jsx                       rule builder canvas
  src/components/                   RuleNode, ProcessingPage, SchedulerPage
  src/api/api.jsx                   calls to /rule_engine/*
backend/automation/               ← Django project (run commands from here)
  manage.py
  requirements.txt
  scheduler.py                      standalone job scheduler process
  automation/                       Django settings / urls / wsgi
  rule_engine/                      the Django app
    models.py                       RuleEngine, RuleList, RuleEdge, RuleLogic, ParamModel,
                                    ClaimsData, RuleEngineProcessed, ScheduledJob,
                                    DailyInventory (read-only MSSQL view)
    registry.py                     @register_function + FUNCTION_REGISTRY
    executor.py                     GraphRuleExecutor
    views.py / urls.py              REST API
    functions/                      all registered functions (one package per macro)
```

---

## The rule engine

### Registering a function

```python
from rule_engine.registry import register_function

@register_function(
    name="release_pend_fetch_from_file",   # unique; shown in the UI
    tag="Release Pend Macro",              # groups nodes in the UI palette
    color="#2e7d32",                       # node colour in the UI
    inputs=[{"name": "location", "type": "str"}],
    outputs=[{"name": "df", "type": "dataframe"}],
)
def release_pend_fetch_from_file(location: str, context=None):
    ...
    return {"df": df}       # merged into the shared context
```

- An input can add `"options": [...]` (rendered as a dropdown) and `"default": ...`.
- A package's functions are registered once it's imported from
  `rule_engine/functions/__init__.py`, for example `from .release_pend_macro import *`.

### How a rule executes (`executor.py`)

- **Start nodes** are the nodes with no incoming edge. The executor runs the graph
  breadth-first from them.
- **Arguments:** for each node it merges `context` with the node's saved params, then passes
  only the keys that match the function's signature. A function that declares `context=` gets
  the whole context dict.
- **Results:** whatever dict the function returns is merged into `context`.
- **Edge conditions:** an edge can carry a condition, a Python expression evaluated against
  the context, such as `len(valid_claims) > 0`. An empty condition always passes.
- **Built-in context keys:** `manual`, `rule_name` and `rule_engine_id`. The
  `*_send_status_to_db` functions use them.
- **Manual vs scheduled:** a run triggered from the UI or API (`manual=True`) executes in the
  web server process. A scheduled run (`manual=False`) executes in a **separate child
  process**.

### REST API (prefix `/rule_engine/`)

| Method | Path | Purpose |
|---|---|---|
| GET | `functions/` | List registered functions with their input/output params |
| POST | `functions/refresh/` | Rebuild the function tables in the DB from the in-memory registry  |
| POST | `rules/save/` | Create a rule, or update it when `rule_id` is sent. Body: `{rule_name, nodes, edges}` |
| GET | `rules/` | List rules |
| GET / DELETE | `rules/<id>/` | Get a rule's graph / delete the rule |
| POST | `rules/<id>/execute/` | Run a rule now (manual mode) |
| GET | `dashboard/` | Processing stats |
| GET | `claims/export/` | Export processed claims as CSV |
| GET / POST | `scheduler/jobs/` | List / create or update scheduled jobs |
| PATCH | `scheduler/jobs/<id>/toggle/` | Pause or resume a job |
| DELETE | `scheduler/jobs/<id>/` | Delete a job |


### Scheduler (`scheduler.py`)

A standalone process that reads the `ScheduledJob` table and runs the linked rule. It
supports these schedule types:

- `interval` (seconds, minutes or hours, including several interval/unit combinations)
- `daily` at a set time
- `weekly` on chosen days
- `once` at a given date

Every 10 seconds it re-checks the table, so jobs you add, pause or delete in the UI's
Scheduler page take effect without a restart.

---

## Converted macros

Every macro follows the same pattern:

- **Inputs:** claim rows come in as a DataFrame from either a `*_fetch_from_file` node
  (xlsx/csv) or a `*_fetch_from_db` node (the read-only `DailyInventory` SQL table).
- **Processing:** a `*_run_batch` node does the mainframe work, spread across **up to 4
  EXTRA! sessions in parallel**.
- **Saving results:** a `*_send_status_to_db` node writes the outcome to `ClaimsData` and
  `RuleEngineProcessed`.
- **Settings:** options that lived in checkbox and dropdown cells on the VBA "MAIN" sheet
  become either **node inputs** or rows in a **`rule_code_ref_template.csv`** (one row per rule
  name, selected by a `RULE` column on each claim).

| Package (`rule_engine/functions/…`) | UI tag | What it does | VBA source |
|---|---|---|---|
| `release_pend_macro/` | Release Pend Macro | Releases or pends claims on CPS (HCFA and UB data entry, TOD updates, inel/AP/PRV codes, denials) | `NewPendRelease_Macro/Modules_*.txt` |
| `claim_split_hcfa/` | Claim Split HCFA | Downloads each HCFA claim's PDF from WebClaims, parses it, and keys the split drafts into CPS | `Macro/*.txt` |
| `claims_split_ub/` | Claims Split UB | Same as above, for UB claims | `Macro/*.txt` |
| `new_line_update_release/` | New Line Update Release | Updates claim/service-line data and releases the claim (repricing, Medicare and MRU calculations) | `Macro/*` |
| `same_day_reversal/` | Same Day Reversal | Same-day draft reversal (`Draft_Reveral_9994`) | *(ported from `Same_Day_Reversal/Main.txt`, `oIShared.txt`; not checked in)* |
| `OI_YES_NO/` | OI Yes NO | Updates Other-Insurance status or Plan ID per cert/claim | *(ported from `OI_YES_NO_Macro_VBA_Code.txt`; not checked in)* |


### Release Pend Macro — `release_pend_macro/`

| Function | Inputs | Notes |
|---|---|---|
| `release_pend_fetch_from_file` | `location` | xlsx/csv with `CLAIM_NO`, `CLAIM_TYPE`, `DRAFTS`, `CERT_NO`, `RULE`, and optional per-row override columns (`NEW_AP_CD`, `NEW_PRV_CD`, `NEW_TOS`, …; see the function's docstring for the full list) |
| `release_pend_fetch_from_db` | `rules` | Claims from `DailyInventory` where `MACRO_RULE` is in the given list |
| `release_pend_get_claim_details` | `dx_code_ref_path`, `aply_grid_prc` | Port of `Get_Claim_Details`: fills in pend code, draft count and claim type, with an optional grid-price check |
| `release_pend_run_batch` | `dx_code_ref_path`, `rule_code_ref_path` | Port of `Release_or_Pend_Claim` |
| `release_pend_send_status_to_db` | — | Saves results |

- **Code:**
  - `script.py`: batch loop and navigation
  - `hcfa.py`: CPS450 data entry
  - `ub.py`: BLX2460 data entry
  - `tod.py`: TOD updates
  - `utils.py`: shared screen helpers
- **Settings:** `rule_code_ref_template.csv` has one row per rule.
  - **Toggle columns** match the VBA's `s1cell_*` control cells, for example `apply_uc`,
    `deny_clm`, `denial_code`, `da`/`da_val`.
  - **Per-claim value columns** match its `s1col_*` columns, for example `new_ap_cd`,
    `new_prv_cd`. They're copied onto a claim only if that claim doesn't already have a value.

### Claim Split HCFA — `claim_split_hcfa/`

The macro runs in two parts:

**Part 1 is web and PDF only, with no emulator needed.** `claim_split_get_edi_details` fetches
each claim's PDF from WebClaims, parses it and writes an Excel workbook.

- **Inputs:** `use_new_api`, `most_recent_image`, `show_pdf`, `show_browser`, `dest_dir`
- **Outputs:** `claims_df`, `service_lines_df`, `xlsx_path`
- **Sheets:** the workbook has the same three sheets as the VBA (Main, ClaimInfo,
  ClaimServiceLInes).

**Part 2 is mainframe entry.** `claim_split_run_batch` keys the split drafts into CPS.

- **Split mode:** `split_option` is `SCRATCH`, `SCRATCH NOT ONLINE` or `NON SCRATCH`.
- **Grouping:** `split_grouping` is by date of service or by diagnosis.
- **Other options:** `two_lines_per_draft`, `get_cps_discount`, `bypass`,
  `remove_existing_inel`, `pos_reference_path`.

Supporting functions:

- **Fetch:** `claim_split_fetch_from_file` takes a `CLAIM_NO` column. For scratch modes it also
  takes `NEW_CERT`, `NEW_CCN`, `NEW_DOS`, `NEWBORN_TYPE` and `NON_NEWBORN_SEQ`.
  `claim_split_fetch_from_db` takes a list of CCNs.
- **Export:** `claim_split_export_excel` re-writes the workbook including split status.
- **Save:** `claim_split_send_status_to_db`.

Code by module:

| File | Role |
|---|---|
| `web_claims.py` | Retrieves the PDF. Two paths: the legacy PHP viewer (`use_new_api=N`) and the new WebClaims JSON API (`use_new_api=Y`) |
| `pdf_backend.py` + `pdf_extract.py` | Reads the PDF by coordinates, the same way the VBA's PDF reader does |
| `excel_export.py` | Writes the workbook |
| `cps_entry.py` | Ports `oScratch`, `oNonScratch` and `oScratchNotOnline` |

The VBA input/output reference is in `Macro/IO_Reference.html`.

### Claims Split UB — `claims_split_ub/`

Same two-part structure, file layout and function names as Claim Split HCFA, with the prefix
`claims_split_ub_`. Differences:

- HCFA claims are reported and skipped.
- `split_grouping` is `BY DATE OF SERVICE` or `NONE`.
- The inel-removal option is called `inel_remove_mode`.

### New Line Update Release — `new_line_update_release/`

| Function | Inputs |
|---|---|
| `new_line_update_release_fetch_from_file` | `location`: one row per **service line** (see `new_line_update_release_input_template.csv`) |
| `new_line_update_release_run_batch` | `reference_path`, `rule_code_ref_path` |
| `new_line_update_release_send_status_to_db` | — |

- **What it ports:** `cmdRun_Click`, plus `Line_Update_Release`, `ClaimDraft_SVCLn_Update` and
  `No_SVCLn_Update` from `oWauben`.
- **Settings:** the MAIN-sheet control panel (RLS code, pend reason, apply UC/DPSV,
  reprice %, …) comes from this package's own `rule_code_ref_template.csv`.
- **Calculations:** `medicare_calc.py` and `mru_calc.py`.

### Same Day Reversal — `same_day_reversal/`

- `same_day_reversal_fetch_from_file` takes `location`, an xlsx/csv with columns `CCN`,
  `CERT_ID`, `BG_SV_DT`.
- `same_day_reversal_run_batch` reverses each claim's drafts.
- `same_day_reversal_send_status_to_db` saves the results.

### OI Yes/No — `OI_YES_NO/`

**Fetch:**

- `oi_yes_fetch_cert_id_seq_from_db` takes `rules` and pulls cert, sequence and roll code from
  `DailyInventory`.
- `oi_yes_fetch_File_from_folder` takes `location`.

**Run:** `oi_yes_run_batch` has these inputs:

| Input | Values |
|---|---|
| `search_by` | `CERT` / `CLAIM` |
| `action` | `UPDATE_OI` / `UPDATE_PLAN_ID` |
| `oi_status` | `YES` / `NO` |
| `bg_sv_dt` | date |
| `level_mode` | — |
| `default_tp` | — |
| `TYPE` | — |

**Save:** `oi_yes_send_status_to_db`.

---

## Other built-in functions


| File | Functions |
|---|---|
| `validation.py` | `validate_required_fields`, `validate_claim_amount_range`, `deduplicate_claims`, `filter_claims_by_status`, `calculate_claim_tax`, `auto_approve_claims`, `merge_claim_lists` |
| `claims.py` | `convert_claims_data_to_csv`, `scrap_claims_from_emulator` |
| `db_function.py` | `fetch_claim_ids_from_db`, `add_scrapped_values_to_db` |
| `reflection_automation.py` | `open_emulator` |
| `helpers.py` | Shared helpers, not registered: `attach_emulator_sessions(n=4)`, `bulk_upsert_claims`, screen helpers |

---

## Prerequisites

The **macros only run on Windows**, because they control the emulator through COM. The
engine and UI alone run anywhere.

| Need | Why |
|---|---|
| Windows 10/11 | `pywin32` COM access to `EXTRA.System` |
| Python 3.13 | Backend |
| Node.js 20+ and npm | UI |
| SQL Server (Express is fine) + **ODBC Driver 18 for SQL Server** | Django database (`mssql-django`) |
| EXTRA! / Reflection, **logged in to CPS with sessions open** | Every `*_run_batch` attaches to running sessions; it doesn't log in for you |
| Microsoft Edge, signed in to WebClaims once | Only for the claim-split macros with `use_new_api=Y` (sign-in reuses an Edge profile via Playwright) |
| Network access to the claims portals | Claim-split PDF download |

---

## Setup and running

All backend commands run from `backend/automation`.

### 1. Backend

```powershell
cd backend\automation
python -m venv ..\env
..\env\Scripts\Activate.ps1
pip install -r requirements.txt

# needed once for pywin32 COM support
python ..\env\Scripts\pywin32_postinstall.py -install
```

`requirements.txt` includes `pywin32`, `pdfplumber`, `openpyxl`,
`requests`, `requests-negotiate-sspi`, `beautifulsoup4` and `playwright`. Playwright uses your
installed Edge (`channel="msedge"`), so there's no `playwright install` step.

### 2. Database

Settings are in `automation/settings.py`. By default they connect to `localhost\SQLEXPRESS`,
database `master`, with Windows authentication (`trusted_connection`). Change `NAME`/`HOST` if
your setup differs (a dedicated database is recommended over `master`). Then create the
tables:

```powershell
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin
```

`DailyInventory` (`TBL_DAILY_INVENTORY_NEW`) is unmanaged and read-only. Django won't create
it; it must already exist for the `*_fetch_from_db` functions to work.

### 3. Run the API

```powershell
python manage.py runserver        # http://127.0.0.1:8000
```

 call **Refresh functions** once after the server starts, and again
after adding or changing a function. You can use the UI button or call it directly:

```powershell
curl -X POST http://127.0.0.1:8000/rule_engine/functions/refresh/
```

### 4. Run the UI

```powershell
cd UI\my-react-flow-app
npm install
npm run dev                       # http://localhost:5173
```

Vite proxies `/rule_engine/*` to `http://localhost:8000`, so start the API first.

### 5. Run the scheduler

Only needed for scheduled rules. Run it in its own terminal:

```powershell
cd backend\automation
python scheduler.py
```

---

## Building and running a rule

1. Open EXTRA!/Reflection, log in to CPS, and leave **1–4 sessions** open. Each `*_run_batch`
   spreads claims across them.
2. In the UI, drag nodes from the palette (grouped by tag) and connect them. Typical chains:

   ```
   release_pend_fetch_from_file → release_pend_run_batch → release_pend_send_status_to_db

   claim_split_fetch_from_file → claim_split_get_edi_details → claim_split_run_batch
                               → claim_split_export_excel → claim_split_send_status_to_db
   ```

3. Fill in node inputs (file paths, dropdowns), name the rule and save it.
4. Click **Run**, or add a job on the **Scheduler** page.
5. Results go to `ClaimsData` and `RuleEngineProcessed`. They appear on the dashboard and can
   be exported from `claims/export/`. The claim-split macros also write an `.xlsx` to
   `dest_dir` (default `%TEMP%`).

The server console prints a detailed log of each claim: screens visited, values keyed and
status. It's the first place to look when a claim doesn't do what you expected.

---

## Adding a function or porting a macro

1. Create `rule_engine/functions/<macro_name>/` with:
   - `__init__.py` (`from .script import *` and `from .helper import *`)
   - `script.py` (the `*_run_batch`)
   - `helper.py` (fetch and send-status functions)
   - `utils.py` (screen primitives: `place_value`, `send_enter`, …)
2. Check the VBA source into `<macro_name>/Macro/`, so later VBA edits can be diffed and ported.
3. Add `from .<macro_name> import *` to `rule_engine/functions/__init__.py`.
4. Use `attach_emulator_sessions()` from `helpers.py` and the same
   `ThreadPoolExecutor`/`Queue` multi-session pattern as the existing macros.
5. Put MAIN-sheet options that change per rule in a `rule_code_ref_template.csv` (one row per
   rule) rather than adding dozens of node inputs.
6. Restart the server, then **Refresh functions**.
7. Because of the `.gitignore` issue below, add new `.py` files with `git add -f`.

When a VBA macro changes, port the change to the matching `.py` module and record the VBA
date tag in a comment (for example `# VBA ADDED 2026.09.01`), as the existing code does.

---

## Troubleshooting and gotchas

- **New `.py` files aren't committed.** `.gitignore` contains a bare `*.py` line. Files already
  in git are still tracked, but a new module needs `git add -f path/to/file.py`. Otherwise it
  silently goes missing on other machines.
- **`TypeError: ... got an unexpected keyword argument ...` at startup or run time.** Your files
  come from different versions, for example a new `script.py` with an older `web_claims.py`.
  Pull the whole branch, or check out the whole package folder
  (`git checkout origin/<branch> -- backend/automation/rule_engine/functions/<pkg>`), instead of
  copying single files.
- **A function is missing from the UI.** Check that its package is imported in
  `functions/__init__.py`. Then restart the server and click **Refresh functions**.
- **`No active emulator sessions found` / `win32com not available`.** EXTRA! isn't running,
  isn't logged in, or `pywin32` wasn't post-installed. Run the post-install command in
  [Setup step 1](#1-backend).
- **Claim split lands on a Microsoft sign-in page.** Run once with `show_browser=Y` and finish
  the Edge sign-in. Later runs reuse the saved profile.
- **TLS:** `web_claims.py` turns off certificate verification (`VERIFY_TLS = False`) because
  the corporate proxy re-signs `*.optum.com`. Revisit this if the network setup changes.
- **Secrets:** `settings.py` has a development `SECRET_KEY` and `DEBUG = True`. Don't deploy it
  as-is.
