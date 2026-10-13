# Rule Engine UI

The web front end for the rule engine. You use it to build workflows by connecting
registered Python functions, save them as rules, run them, schedule them and watch the
results.

It's a single-page **React 19** app built with **Vite 7** and
**[React Flow](https://reactflow.dev/) (`@xyflow/react` 12)**. It talks to the Django API in
`backend/automation`. For the backend, the rule-engine concepts and the macros themselves,
see the [repository README](../../README.md).

> **Branches:** this README describes the UI on `hotfix-7-oct`. The UI on `dev`/`main` is
> older. It has no **Refresh Functions** button, no colour-grouped function picker (the
> backend's `tag`/`color` metadata only exists on the hotfix branches), and an earlier
> dashboard.

---

## Quick start

```powershell
# 1. Start the backend first (from backend/automation, venv active)
python manage.py runserver           # → http://127.0.0.1:8000

# 2. Start the UI
cd UI\my-react-flow-app
npm install
npm run dev                          # → http://localhost:5173
```

Open <http://localhost:5173>. The UI fetches functions, rules and dashboard data from the
API on load, so the backend must be running.

| Script | What it does |
|---|---|
| `npm run dev` | Dev server with hot reload on port 5173 |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Serves the `dist/` build locally |
| `npm run lint` | ESLint (`eslint.config.js`) |

Requires **Node.js 20+** (Vite 7's minimum is 20.19).

### How the UI reaches the API

The UI reaches the API in two different ways:

- **Through the Vite proxy (relative URLs):** most calls in `src/api/api.jsx` use the relative
  path `/rule_engine/...`, which `vite.config.js` proxies to `http://localhost:8000`.
- **Direct to `http://127.0.0.1:8000` (hard-coded):** saving a rule (`saveGraph`), the
  dashboard and CSV export (`App.jsx`), and everything on the Scheduler page
  (`SchedulerPage.jsx`). These calls depend on the backend's CORS settings, which allow
  `localhost:5173` and `127.0.0.1:5173`.

So the API must be on port 8000 of the same machine. Running it anywhere else means changing
those hard-coded URLs too (see [Known issues](#known-issues)).

---

## Using the app

The top bar has three pages.

### ⏱ Dashboard (default page)

Shows processing results from `GET /rule_engine/dashboard/`.

- **Day-wise Summary:** claims processed per day. Click a day to drill in.
- **Rule-wise Details:** each run for that day (time, rule, claim count) with *Processed*,
  *Already Released*, *Unprocessed* and *Total* counts. Each row can export its claims to CSV
  via `GET /rule_engine/claims/export/`.

### ⬡ Workflow (the rule builder)

**The left sidebar** lists saved rules.

- Click a rule to load its graph.
- Click **+** to start a new, empty workflow.
- Use the delete icon (with a confirmation step) to remove a rule.

**The toolbar:**

| Button | What it does | When it's enabled |
|---|---|---|
| **Add Function** | Opens the function picker | New workflow, or an existing rule in edit mode |
| **Refresh Functions** | Calls `POST /functions/refresh/`, then reloads the list. Use it after adding or changing a backend function | Always |
| **Save Workflow** | New workflow: asks for a rule name. Edit mode: saves over the loaded rule | Unsaved nodes exist, or edit mode |
| **Execute Flow** | Runs the loaded rule now (`POST /rules/<id>/execute/`) | A saved rule is loaded and you're not in edit mode |
| **Edit Flow / Cancel Edit** | Unlocks a loaded rule for changes; *Cancel Edit* restores the saved version | A rule is loaded |

**To build a workflow:**

1. Click **+** in the sidebar, or load a rule and click **Edit Flow**.
2. Click **Add Function**. The picker is searchable and grouped by each function's `tag`,
   colour-coded with its `color`. Pick a function and click **Add**.
3. The new node immediately opens a **parameters dialog**, with one field per function input.
   The field type depends on the input:

   | Backend input definition | Field shown |
   |---|---|
   | has `options: [...]` | dropdown |
   | `type: "date"` | date picker |
   | anything else | text box |

   Fields start at the input's `default`. You can leave inputs that a previous node supplies
   through the shared context (such as `df`) empty.
4. Drag from a node's **bottom handle** to the next node's **top handle** to connect them. The
   executor runs nodes in that order and passes each node's outputs forward.
5. In edit mode, **double-click** a node's parameter block to change its parameters, or click
   **−** to delete the node.
6. Click **Save Workflow**, then **Execute Flow**.

For example, a Release Pend rule is three nodes:

```
release_pend_fetch_from_file  →  release_pend_run_batch  →  release_pend_send_status_to_db
   location = C:\...\claims.xlsx     rule_code_ref_path = C:\...\rule_code_ref.csv
```

File paths are read **by the backend**, so they must be valid on the machine running Django,
not the browser's machine.

### ⏱ Scheduler

This page manages `ScheduledJob` rows. `backend/automation/scheduler.py` runs the jobs in its
own process, so that process must be running too.

**To create a job,** fill in the job name and pick a rule, then choose a schedule type:

| Type | Settings |
|---|---|
| Interval | Number plus seconds/minutes/hours. Optionally, several interval and unit combinations |
| Daily | Time |
| Weekly | Time and days |
| Run Once | Date and time |

**Per-job actions:** run now, pause/resume, delete.

**Page-wide actions:** pause/resume all, execute all.

---

## Project structure

```
index.html
vite.config.js            Vite config + /rule_engine proxy → localhost:8000
eslint.config.js
src/
  main.jsx                React entry point
  App.jsx                 Top bar, page switching, the whole Workflow page
                          (canvas, sidebar, dialogs, save/load/run) and dashboard data loading
  App.css, index.css
  api/api.jsx             Rule/function API calls (load/save/delete/execute rules, functions, refresh)
  components/
    RuleNode.jsx          Custom React Flow node: name, params preview, edit/delete in edit mode
    ProcessingPage.jsx    Dashboard page
    SchedulerPage.jsx     Scheduler page (makes its own fetch calls)
public/                   Static assets
```

Styling is inline style objects, with no CSS framework. State is plain React `useState` in
`App.jsx`, with no router or state library. Pages switch on a `currentPage` value.

---

## What gets saved

**Save Workflow** posts this to `POST /rule_engine/rules/save/`. It includes `rule_id` only
when updating an existing rule:

```json
{
  "rule_name": "Release pend - rule 2",
  "nodes": [
    { "id": "node-1728912345678",
      "data": { "function_name": "release_pend_fetch_from_file",
                "params": { "location": "C:\\data\\claims.xlsx" } } }
  ],
  "edges": [
    { "source": "node-1728912345678", "target": "node-1728912349999" }
  ],
  "rule_id": 12
}
```

The backend stores the graph in the `RuleList` and `RuleEdge` tables, plus a `reactflow_json`
copy that the UI uses to redraw the graph when the rule is loaded.

---

## API calls used

All paths below are under `/rule_engine/`.

| Call | Used for |
|---|---|
| `GET functions/` | Function picker (name, tag, colour, inputs) |
| `POST functions/refresh/` | Refresh Functions button |
| `GET rules/` · `GET rules/<id>/` · `DELETE rules/<id>/` | Sidebar: list / load / delete |
| `POST rules/save/` | Save Workflow |
| `POST rules/<id>/execute/` | Execute Flow, Scheduler "run now" |
| `GET dashboard/` | Dashboard page |
| `GET claims/export/` | Dashboard CSV export |
| `GET/POST scheduler/jobs/` · `PATCH scheduler/jobs/<id>/toggle/` · `DELETE scheduler/jobs/<id>/` | Scheduler page |

---

## Known issues

These were found while writing this README and **haven't been fixed**:

- **Scheduler → "Execute all" doesn't run anything.** It calls `rules/<rule_name>/execute/`,
  but the route needs the numeric rule id (`job.rule_id`, as the per-job "run now" button
  correctly uses). Every call returns 404. `fetch` doesn't reject on a 404, so the page still
  says the jobs ran.
- **Scheduler → "Run Once" never gets a valid date.** The page sends
  `schedule_config.datetime`, but `scheduler.py` reads `schedule_config.date` and `time`. The
  two need to agree on one format.
- **Edge conditions can't be set from the UI.** The backend supports a Python condition on
  each edge (for example `len(df) > 0`), but the UI saves edges with only `source` and
  `target`, so every edge always fires.
- **Some API URLs are hard-coded to `http://127.0.0.1:8000`** (see
  [How the UI reaches the API](#how-the-ui-reaches-the-api)). Moving everything to the relative
  `/rule_engine` path behind the proxy would make the backend address configurable in one
  place.
- **Execute Flow waits for the whole rule.** The request returns only when every node has
  finished, which can take many minutes for a large macro batch. The rule keeps running on the
  server even if the browser gives up. Follow progress in the Django console.
