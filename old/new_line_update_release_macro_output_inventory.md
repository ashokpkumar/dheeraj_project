# New Line Update Release Macro — Output Inventory

Companion to `new_line_update_release_macro_input_inventory.md`. This tracks the other direction: every cell/property/log entry the macro **writes back to**, rather than reads from. Outputs fall into 3 buckets: spreadsheet result cells, non-cell side effects (metadata/logging), and the destination-system (mainframe) field writes that are the actual point of the macro.

---

## Overview — what the macro actually does

In plain terms: it's an automated data-entry clerk for the mainframe claims system. Claims examiners today have to open a claim on their terminal, find the right line item, correct the numbers/codes on it, and then either finalize (release) or hold (pend) the claim — one claim at a time, all by hand. This macro does that same clicking-and-typing work automatically, for a whole batch of claims at once.

### The data, and where it comes from/goes

There are really two kinds of information involved:

1. **"Which claims, and what should change on them"** — a list of claim numbers, and for each claim, the specific service lines that need correcting (the date of service, procedure, and charge amount identify *which* line), along with the new values to put on that line: the correct denial/ineligibility code and dollar amount, corrected modifiers, a corrected charge amount, other-insurance dollar amounts, and so on. This is the claim-specific work list — it comes from whatever source has the corrections (a spreadsheet, a report, a database extract).

2. **"How to handle every claim in this batch"** — settings that apply the same way across a whole run: what release code to use, whether to release or pend, who gets paid, follow-up notes, whether to auto-bypass certain mainframe warnings, etc. This is configured once per batch rather than typed per claim.

Two optional calculators can fill in part of bucket #1 automatically before the batch runs, instead of someone typing the numbers by hand:
- One works out how much of a claim's total Medicare deduction/other-insurance amount belongs to each individual service line.
- The other looks up the correct negotiated/contracted rate for a service line (based on the year, the state, and whether the provider is in- or out-of-network) and calculates what the new line amount should be.

### How it actually does the work

For each claim in the batch, the macro:

1. **Opens the claim** on the mainframe, the same way a person would by typing the claim number in.
2. **Finds every "draft"** (version) of that claim that needs work.
3. For each draft, **finds the matching service line on screen** — since the screen doesn't necessarily show lines in a predictable order, it identifies the right one by comparing the date, procedure, units, charge amount and modifiers already on screen against what's in the work list, before touching anything.
4. **Types in the corrections** on that line — the new code, new amount, new modifiers, other-insurance figures, whatever was specified — exactly like an examiner keying it in.
5. **Handles the interruptions along the way** — the mainframe throws up various screens mid-process (a duplicate-claim warning, a provider-change prompt, a "date is before the condition started" error) and the macro knows how to respond to each one so a person doesn't have to babysit it.
6. **Finalizes the draft** — either releases it (pays/finalizes the claim) or pends it (parks it for someone to review), based on how the batch was configured.
7. **Writes back a result** for every claim — released, pended, or a plain-English reason it couldn't finish (claim not found, provider change failed, line didn't match, etc.) — so whoever ran the batch can see exactly what happened afterward.

Because each claim is independent, the macro can also run several mainframe sessions side by side, so a batch of hundreds of claims finishes in a fraction of the time a single person working one screen at a time would take — without changing anything about *how* each claim gets handled, just how many get handled in parallel.

---

## 1. Spreadsheet result/status cells

| # | Cell/Col | Purpose | Written by | Code ref |
|---|---|---|---|---|
| 1 | `B` `colClmTyp` | CLAIM TYPE — auto-detected ("UB"/"HCFA") from the draft screen | `Line_Update_Release` | `oWauben` L139, L163 |
| 2 | `C` `colDraft` | DRAFTS — count of drafts found for the claim | `Line_Update_Release` | `oWauben` L70 |
| 3 | `D` `colExMsg` | EXCEPTION MESSAGE — accumulated status/failure text (written from ~10 different points: claim-not-found, provider-change-failed, screen-not-mapped, CCN rejected, released/pended, etc.) | `Line_Update_Release`, `ClaimDraft_SVCLn_Update` | `oWauben` L67,73,126,136,186,202,217,239,276,293,300,305-309,473,563,574 |
| 4 | `AL` `colStat` | MACRO STATUS — `"DONE"` per matched service line, or an error state | `ClaimDraft_SVCLn_Update`, `MEDICARE_CALCULATION`, `cdmMRU_Click` | `oWauben` L469,559; L604,616; `Main.txt` L32,42 |
| 5 | `P` `colNwAmt` | NEW INEL1 AMOUNT — computed reprice amount | `cdmMRU_Click` (MRU calc), `chkReprice_Click` (reprice %) | `Main.txt` L37,39,62 |
| 6 | `Y` `colOIEligAmt` | OI ELIG AMT — computed Medicare-OI eligible amount | `MEDICARE_CALCULATION` (TYPE B) | `oWauben` L624 |
| 7 | `Z` `colOIPdAmt` | OI PAID AMT — computed Medicare-OI paid amount | `MEDICARE_CALCULATION` (TYPE B) | `oWauben` L630 |
| 8 | `I1` | CUR RW — runtime progress tracker (which row is currently processing) | `Line_Update_Release` | `oWauben` L45 |

**Note on #5–7:** these three are *dual-role* — the same columns are counted as inputs in the Input Inventory (a user can type values in directly), but they're also valid macro *outputs* when populated by the MRU/Medicare calc buttons instead. Not double-counted as new fields here, just flagged as write targets.

**Subtotal: 8 spreadsheet cells/columns.**

---

## 2. Non-cell side effects

| # | Output | Trigger | Code ref |
|---|---|---|---|
| 9 | `MsgBox "MACRO IS FINISHED"` completion notice | end of `cmdRun_Click` / `cmdMedCalc_Click` | `Main.txt` L98, L130 |
| 10 | AAI usage-tracking log entry (external VBS script call, 1 per run) | `USAGE_LOG_AAI` | `AAIUtilization` L160-183; called from `Main.txt` L96,128 |
| 11-17 | 7 workbook `BuiltinDocumentProperties` fields: Title, Keywords, Comments, Document version, Category, Subject, Revision number | `SET_MACRO_FILE_PROPERTIES`, runs on every `Workbook_Open` | `AAIUtilization` L53-65 |

**Subtotal: 2 event-type outputs + 7 metadata properties = 9.**

---

## 3. Destination-system (mainframe/CPS) field writes — the macro's actual purpose

Every `PLACEVALUE`/`REMOVEVALUE` call inside `Line_Update_Release` / `ClaimDraft_SVCLn_Update` pushes a value onto a CPS450.01 / BLX2460.01 / CPS506.01 / CPS310.01 / CPS910.01 mainframe screen field — that write **is** the claim update the macro exists to perform. From the workbook's side these are the same "new value" columns already itemized in the Input Inventory; from the claims-system's side, they're outputs. Full field-by-field breakdown below, grouped by destination screen, in the order the macro visits them (`row, col` is the screen coordinate `PLACEVALUE`/`REMOVEVALUE` targets).

### 3a. CPS520.01 — claim search

| Action | Position | Value | Notes |
|---|---|---|---|
| PLACEVALUE | (8,15) | `CLAIM_NO` | Claim-control-number entry; repeated on every navigation-back-to-list cycle |

### 3b. CPS310.01 — provider change sub-flow (only when `chg_provider=Y`)

Triggered from the draft screen by placing `"X"` at (29,26) then ENTER:

| Action | Position | Value | Notes |
|---|---|---|---|
| PLACEVALUE | (29,26) | `"X"` | Opens the provider-change screen |
| REMOVEVALUE | (3,27) | — | Clears existing provider selection |
| PLACEVALUE | (5,69) | `PRV_ZIP` (M8) | |
| PLACEVALUE | (7,30) | `PRV_INT_NBR` (M7) | |

Fails the draft (`"PROVIDER CHANGE FAILED."`) if the screen isn't CPS310.01 after this.

### 3c. BLX2460.01 — UB claim/draft screen, header fields

| Action | Position | Value | Condition |
|---|---|---|---|
| REMOVEVALUE | (22,6) | — | `remove_prv=Y` |
| PLACEVALUE | (22,6) | `NEW_PRV_VAL` (claim-level) | always |
| REMOVEVALUE | (12-15, 18) and (12-15, 30) | — | `inel2_option="REMOVE INEL2 AMTCD"` |
| REMOVEVALUE | (18-21, 2), (18-21, 14), (18-21, 26) | — | `rem_oi_elig_amt=Y` |
| PLACEVALUE | (29,71) | `"X"` | `apply_uc=Y` |
| PLACEVALUE | (2,5) | `"RP"` | `apply_rp_bypass_precert=Y` (chkBp) |
| PLACEVALUE | (2,63) / (2,75) | SERV date (6,17) | `change_from_to_dates=Y`, only when FROM/THRU differ from SERV |

### 3d. BLX2460.01 — UB service-line rows (i = 6,7,8,9; `a` = AP column offset 0,3,6,9)

Per matched line (skipped once a line is marked `_STATUS="DONE"`):

| Action | Position | Value |
|---|---|---|
| PLACEVALUE | (i,40) | `NEW_CHRG_AMT` |
| PLACEVALUE | (10, 54+a) | `AP` |
| PLACEVALUE | (i,52) | `NEW_MOD01` |
| PLACEVALUE | (i,56) | `NEW_MOD02` |
| PLACEVALUE | (i,60) | `NEW_MOD03` |
| PLACEVALUE | (i+6,2) + (i+6,14) | `NEW_INEL1_AMOUNT` + `NEW_INEL1_CD` (or `inel_code_val` fallback) — when `inel_cd_fld` is `1` or blank |
| PLACEVALUE | (i+6,18) + (i+6,30) | same pair, INEL2 slot — when `inel_cd_fld="2"` |
| PLACEVALUE | (i+6,2/14/18/30) | INEL1 + INEL2 amount/code, all four — when `inel_cd_fld="BOTH"` |
| PLACEVALUE | (i+6,30) | `"001"` | `inel2_option="APPLY 001 INELCD2"` |
| PLACEVALUE | (i+6,50) | `PROV_RATE` |
| PLACEVALUE | (i+6,62) | `SMB_ADJ_AMT` |
| PLACEVALUE | (i+6,74) | `SMB_ADJ_REASON` |
| PLACEVALUE | (i+12,2) + (i+12,14) | `OI_ELIG_AMT` + `OI_PAID_AMT` — `apply_oi_amt=Y` |
| PLACEVALUE | (i+12,26) | `"B"` | `oi_calc_type="TYPE B"` |
| PLACEVALUE | (i+12,26) | `OI_TYPE` (row value, overrides the above) |
| PLACEVALUE | (i,32) | `BU` |
| PLACEVALUE | (i,36) | `IU` |
| PLACEVALUE | (i,14) | `NEW_TOS` |

### 3e. CPS450.01 — HCFA claim/draft screen, header fields

| Action | Position | Value | Condition |
|---|---|---|---|
| REMOVEVALUE | (26,9) | — | `remove_prv=Y` |
| PLACEVALUE | (26,9) | `NEW_PRV_VAL` (claim-level) | always |
| REMOVEVALUE | (14-17, 18) and (14-17, 30) | — | `inel2_option="REMOVE INEL2 AMTCD"` |
| REMOVEVALUE | (20-23, 4), (20-23, 16), (20-23, 28) | — | `rem_oi_elig_amt=Y` |
| PLACEVALUE | (29,69) | `"X"` | `apply_uc=Y` |
| PLACEVALUE | (2,6) | `new_pos` (formatted `00`) | once per draft, before the line loop |

### 3f. CPS450.01 — HCFA service-line rows (i = 5,7,9,11; `L` = 9→6, `p` = 15→12, stepping down each iteration)

| Action | Position | Value |
|---|---|---|
| PLACEVALUE | (i,21) | `NEW_CHRG_AMT` |
| PLACEVALUE | (i+p,68) | `AP` |
| PLACEVALUE | (i,47) | `NEW_MOD01` |
| PLACEVALUE | (i,51) | `NEW_MOD02` |
| PLACEVALUE | (i,55) | `NEW_MOD03` |
| PLACEVALUE | (i+L,2) + (i+L,14) | `NEW_INEL1_AMOUNT` + `NEW_INEL1_CD` (or fallback) — `inel_cd_fld` `1`/blank |
| PLACEVALUE | (i+L,18) + (i+L,30) | same pair, INEL2 slot — `inel_cd_fld="2"` |
| PLACEVALUE | (i+L,2/14/18/30) | INEL1 + INEL2, all four — `inel_cd_fld="BOTH"` |
| PLACEVALUE | (i+L,30) | `"001"` | `inel2_option="APPLY 001 INELCD2"` |
| PLACEVALUE | (i+L,50) | `PROV_RATE` |
| PLACEVALUE | (i+L,62) | `SMB_ADJ_AMT` |
| PLACEVALUE | (i+L,74) | `SMB_ADJ_REASON` |
| PLACEVALUE | (i+L+6,5) + (i+L+6,16) | `OI_ELIG_AMT` + `OI_PAID_AMT` — `apply_oi_amt=Y` |
| PLACEVALUE | (i+L+6,31) | `BN_QTY` |
| PLACEVALUE | (i+L+6,36) | `BN_AMT` |
| PLACEVALUE | (i+L+6,28) | `OI_TYPE` |
| PLACEVALUE | (i,33) | `OC` |
| PLACEVALUE | (i,74) | `BU` |
| PLACEVALUE | (i,78) | `IU` |
| PLACEVALUE | (i,4) | `NEW_BGN` |
| PLACEVALUE | (i,11) | `NEW_END` |
| PLACEVALUE | (i,18) | `NEW_TOS` |

### 3g. Screen-recovery writes (`rTry` loop)

| Screen seen | Action | Notes |
|---|---|---|
| BLX2460.01 while claim type is HCFA | PF8 → PLACEVALUE `"450"` (2,37) → ENTER → PLACEVALUE `"X"` (29,76) if `apply_dpsv≠N` → ENTER | wrong screen, navigate back |
| CPS450.01 while claim type is UB | PF8 → PLACEVALUE `"460"` (2,37) → ENTER → PLACEVALUE `"X"` (29,78) if `apply_dpsv≠N` → ENTER | wrong screen, navigate back |
| "PRIOR TO CND ONSET" error | PF8 → PLACEVALUE `"910"` (2,37) → ENTER → PLACEVALUE `new_cond_onset_dt` formatted `MMDDYY` (5,24) → ENTER | only when `change_cond_onset_dt=Y` |
| CPS445.01 (duplicate-claim check) | ENTER → re-navigate to correct 450/460 if needed → PLACEVALUE `"X"` at (29,76) HCFA / (29,78) UB → ENTER | auto-bypass duplicate warning |

### 3h. CPS506.01 — release/pend screen (`data_entry_cps506_line_update`)

| Action | Position | Value |
|---|---|---|
| PLACEVALUE | (3,13) | `rls_code` (G4) |
| PLACEVALUE | (3,39) | `lst_rls` (G5) |
| PLACEVALUE | (3,53) | `pnd_rsn` (G6) |
| PLACEVALUE | (4,13) | `pnd_op_id` (I4), then `ROUTE_TO_OPID` (claim-level) overrides if non-blank |
| PLACEVALUE | (4,38) | `flw_up_days` (I5) |
| PLACEVALUE | (4,50) | `note` (G7) |
| PLACEVALUE | (5,24) | `eob` (K4) |
| PLACEVALUE | (5,31) | `ck` (K5) |
| PLACEVALUE | (5,39) | `dci` (K6) |
| PLACEVALUE | (7,8) | `payee` (K7) |
| PLACEVALUE (word-wrapped, 43 chars/line) | (16+, col 36) | `eob_note` (G8), via `Place_EOB_Notes` |

Draft is cancelled without a release attempt (`"DRAFT:i CANCELLED: CHANGE PAYEE TO 1"`) if the screen shows payee `"1"` but `payee` setting is `"0"`.

### 3i. System-reset action (unmapped screen recovery)

Not a claims-data write — a session-recovery sequence when the macro lands on an unrecognized screen at claim entry:

| Action | Position | Value |
|---|---|---|
| PF22 | — | — |
| PLACEVALUE | (31,15) | `"i GJBB"` |
| ENTER | — | — |
| PLACEVALUE | (31,15) | `"GJBB"` |
| ENTER | — | — |
| PF9 | — | — |

### Summary

| Source (Input Inventory) | Destination screen field(s) |
|---|---|
| Claim-level: `ROUTE_TO_OPID` (E), `NEW_PRV_VAL` (F) | CPS506 OPID (4,13); CPS450/BLX2460 provider field (26,9)/(22,6) |
| MAIN control panel release fields: RLS, LST RLS, PEND RSN, FLUP DAYS, NOTE, EOB, CK, DCI, PAYEE, EOB NOTE (11 fields) | CPS506.01, rows 3-7 |
| Service-line "new value" columns: AP, NEW INEL1/2 AMT/CD, NEW MOD01-03, SMB ADJ AMT/REASON, OI ELIG/PAID AMT, OI TYPE, BU, IU, OC, PROV RATE, NEW BGN/END/TOS, NEW CHRG AMT, BN QTY/AMT (~24 fields) | CPS450.01 / BLX2460.01 service-line rows |

**≈ 37 distinct mainframe field targets** (11 + 2 + 24) receive writes per claim/draft — this is the same field set as the Input Inventory's CLAIM LEVEL + SERVICE LINE + relevant MAIN-panel columns, just counted from the output side instead of the input side.

---

## Grand Total (spreadsheet-visible outputs only)

| Category | Count |
|---|---|
| Spreadsheet result/status cells | 8 |
| Non-cell events (MsgBox, AAI log) | 2 |
| Workbook metadata properties | 7 |
| **Total distinct spreadsheet-visible outputs** | **17** |

Plus **≈37 mainframe field writes per claim/draft** (Section 3) — not a fixed "spreadsheet output" count since it repeats per claim/draft processed, but this is the actual deliverable of the macro.

---

## Mapping to the Python port

| Original output | Where it landed in the port |
|---|---|
| `colClmTyp`, `colDraft` | Not persisted as separate columns — folded into the returned `MACRO STATUS` string / detected inline per draft in `_process_line_update_claim` |
| `colExMsg` / `colStat` | `result` list item: `{"CLAIM CONTROL #": ..., "MACRO STATUS": ...}`, returned by `new_line_update_release_run_batch` |
| `colNwAmt` (MRU calc) | `NEW_INEL1_AMOUNT` column in the `df` returned by `new_line_update_mru_repricing_calc`, plus its own `result` status list |
| `colOIEligAmt` / `colOIPdAmt` (Medicare calc) | `OI_ELIG_AMT` / `OI_PAID_AMT` columns in the `df` returned by `new_line_update_medicare_oi_calc`, plus its own `result` status list |
| `I1` CUR RW | Not needed — batch processing has no single "current row" UI cell; progress is implicit in per-claim results |
| MsgBox completion notice | Not applicable in batch/headless mode — `success: bool` on the return dict instead |
| AAI usage log | Not ported (that tracking system is specific to the Excel/VBA macro fleet) |
| Document-property metadata | Not applicable — no workbook to attach properties to |
| Mainframe field writes (Section 3) | `place_value()`/`remove_value()` calls in `utils.py`'s `update_hcfa_service_lines` / `update_ub_service_lines` / `data_entry_cps506_line_update` |

See `new_line_update_release_macro_reference.md` for the registered functions' own `inputs`/`outputs` (the `@register_function` decorator signatures: `success`/`df`/`result` etc.) — that's a different, smaller "output" concept (pipeline node outputs), not the macro's write-back cells covered here.
