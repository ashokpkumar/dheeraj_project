# New Line Update Release Macro — Functional Reference

## File Overview

| File | Role |
|------|------|
| `script.py` | Main orchestrator — `new_line_update_release_run_batch()`, rule CSV loading, claim navigation, per-draft loop (ports `cmdRun_Click` → `Line_Update_Release`) |
| `utils.py` | Screen data-entry helpers + matching/reference logic (ports `ClaimDraft_SVCLn_Update`, `No_SVCLn_Update`, `Place_EOB_Notes`, `IS_IT_MATCHING`, `RTN_PND_CODE`, `OOP_Claim`, `SetInelCdList`) — imports the CPS520 screen primitives from `release_pend_macro.utils` instead of duplicating them |
| `medicare_calc.py` | Standalone pre-step: `new_line_update_medicare_oi_calc()` — Medicare OI dollar calc (ports `cmdMedCalc_Click` → `MEDICARE_CALCULATION`) |
| `mru_calc.py` | Standalone pre-step: `new_line_update_mru_repricing_calc()` — MRU repricing calc (ports `cdmMRU_Click` → `MRU_CALC_SETTINGS`) |
| `rule_code_ref_template.csv` | Template for the rule CSV — one row per `RULE`, columns match the settings flags below |
| `__init__.py` | Re-exports all three registered functions |
| `Macro/*.txt` | Original VBA source the Python ports are checked against (`Main.txt`, `oWauben`, `oColumnMapping`, `oShared`, `Reference`, `ThisWorkbook.txt`) |

Unlike `release_pend_macro`, this macro is split into **three separately-registered pipeline functions** — the two calc steps are pure (no emulator) and are meant to run *ahead of* the release step, populating columns it reads:

```
new_line_update_medicare_oi_calc  ─┐
new_line_update_mru_repricing_calc ─┼─► new_line_update_release_run_batch
                     (optional)     ┘
```

---

## Input Shape

`context['df']` is **one row per SERVICE LINE** (not one row per claim/draft), fetched upstream by a separate DB/file function. Expected columns (mirrors `Macro/oColumnMapping`):

| Group | Columns |
|-------|---------|
| Claim-level (carried on every line of the claim) | `CLAIM_NO`, `RULE`, `ROUTE_TO_OPID`, `NEW_PRV_VAL` |
| Match criteria (blank = don't care) | `BGN_SV_DT`, `CPT`, `LINE_CHG_AMT`, `UNITS`, `MOD01`, `MOD02`, `MOD03` |
| New values to apply | `AP`, `NEW_INEL1_AMOUNT`, `NEW_INEL1_CD`, `NEW_INEL2_AMOUNT`, `NEW_INEL2_CD`, `NEW_MOD01`, `NEW_MOD02`, `NEW_MOD03`, `SMB_ADJ_AMT`, `SMB_ADJ_REASON`, `OI_ELIG_AMT`, `OI_PAID_AMT`, `OI_TYPE`, `BU`, `IU`, `OC`, `PROV_RATE`, `NEW_BGN`, `NEW_END`, `NEW_TOS`, `NEW_CHRG_AMT`, `BN_QTY`, `BN_AMT` |

`OI_ELIG_AMT` / `OI_PAID_AMT` and `NEW_INEL1_AMOUNT` can instead be left blank and populated by chaining `new_line_update_medicare_oi_calc` / `new_line_update_mru_repricing_calc` ahead of the release step.

---

## 1. `new_line_update_medicare_oi_calc(reference_path, oi_type)` — `medicare_calc.py`

Pure calculation, no emulator. Groups `context['df']` by `CLAIM_NO`.

**`_calc_claim(lines, oi_type, med_calc)`:**

1. Look up `claim_no` in `med_calc` (from the reference file's `MED_CALC_*` columns: `ded_coin_eob`, `neg_contractual`, `noncov`) → if missing: `"NO MED CALC SET."`
2. Sum `LINE_CHG_AMT` across lines → `t_billed`
3. `t_billed_less_noncov = t_billed - noncov`; if it differs from `t_billed` (i.e. `noncov` is non-zero) → `"MED CALC AMT FAILED."` *(ported as-written from VBA — this only ever passes when `noncov` is 0; flagged as a likely pre-existing bug, kept for parity)*
4. `pct_chrg = round(1 - (ded_coin_eob / t_billed_less_noncov), 9)`
5. **`oi_type == "TYPE B"`** (the only implemented branch):
   - Per line: `OI_ELIG_AMT = LINE_CHG_AMT`; accumulate `t_md_pd_b4_check = round(OI_ELIG_AMT * pct_chrg, 2)`
   - `t_billed_less_md_pd_b4_check = t_billed - t_md_pd_b4_check`
   - Per line (`_rtn_oi_paid_amt`, 1-indexed `i`):
     - `i > 1` → `OI_PAID_AMT = round(OI_ELIG_AMT * pct_chrg, 2)`
     - `i == 1` and `t_billed_less_md_pd_b4_check == ded_coin_eob` → same as above
     - `i == 1` and `<` → above **minus** the shortfall
     - `i == 1` and `>` → above **plus** the excess
   - Returns `"OK"`
   - Other `oi_type` values are not implemented in the source VBA → `"OI TYPE NOT IMPLEMENTED"` (no-op)

Returns `{"success", "df": updated_df, "result": [{CLAIM CONTROL #, MACRO STATUS}, …]}`.

---

## 2. `new_line_update_mru_repricing_calc(mru_info_path, reference_path)` — `mru_calc.py`

Pure calculation, no emulator. Reads the **MRU REPRICING INFO** table (`mru_info_path`: `CLAIM_NO`, `BGN_SV_DT`, `CPT`, `LINE_CHG_AMT`, `UNITS`, `MOD01-03`, `POS`, `PRV` — `PRV` is the 2-letter state code).

**`_match_mru_rows(mru_rows, ln)`** — filters `mru_rows` to the ones matching `ln` on `CLAIM_NO` + whichever of `BGN_SV_DT` / `CPT` / `LINE_CHG_AMT` / `UNITS` / `MOD01-03` are populated on the line (blank = don't care, via `is_it_matching`).

Per service line:
1. Match against `mru_rows` → **must resolve to exactly 1 row**, else `"UNABLE TO CALCULATE"`
2. `key = Year(mru.BGN_SV_DT) + mru.PRV`; look up in `mru_calc` (reference `MRU_*` columns) → missing: `"NO MRU CALC SET"`
3. `pos = mru.POS.zfill(2)`; `pct = ip_pct if pos in mru_innetwork_pos else out_pct`
4. `NEW_INEL1_AMOUNT = round(LINE_CHG_AMT * pct, 2)` → `"OK"`

Returns `{"success", "df": updated_df, "result": [{CLAIM CONTROL #, MACRO STATUS, NEW_INEL1_AMOUNT}, …]}`.

---

## 3. `new_line_update_release_run_batch(reference_path, rule_code_ref_path)` — `script.py`

### Setup (runs once)

| Function | What it does |
|----------|--------------|
| `load_line_update_reference(reference_path)` | Reads the reference file (CSV/XLSX, mirrors `Macro/Reference`) → dict below |
| `_load_rule_code_ref(rule_code_ref_path)` | Reads rule CSV → `{RULE_UPPER: {col: val, …}}`, same shape as `release_pend_macro` |
| `attach_emulator_sessions(n=4)` | Attaches to up to 4 **live** EXTRA emulator sessions (helper shared across macros, `rule_engine.functions.helpers`) |

**`load_line_update_reference` return dict:**

| Key | Source | Purpose |
|-----|--------|---------|
| `hcfa_inelcd` | col `HCFA_INELCD` | Valid ineligibility codes for HCFA service-line matching |
| `ub_inelcd` | col `UB_INELCD` | Valid ineligibility codes for UB service-line matching |
| `exception_inel_codes` | col `EXCEPTION_INEL_CODES` | Codes exempt from the inel-code match check |
| `mru_innetwork_pos` | col `MRU_INNETWORK_POS` | POS codes treated as in-network for MRU repricing (zero-padded to 2 digits) |
| `med_calc` | cols `MED_CALC_CLAIM_NO/DED_COIN_EOB/NEG_CONTRACTUAL/NONCOV` | `{claim_no: (ded_coin_eob, neg_contractual, noncov)}` |
| `mru_calc` | cols `MRU_YEAR/STATE/IP_PCT/OUT_PCT` | `{year+state: (ip_pct, out_pct)}` (percents normalized to fractions) |

`"BLANK"` literal entries in the code-list columns map to `""`.

### Multi-session parallel processing (unique to this macro)

Unlike `release_pend_macro` (single EXTRA session, sequential), this macro:
1. Attaches up to **4** emulator sessions via `attach_emulator_sessions(n=4)`
2. Groups `context['df']` rows into claims (`{claim_no: [service-line rows]}`)
3. Round-robins claims across `worker_count = min(4, len(sessions))` buckets
4. Runs one `ThreadPoolExecutor` worker per session (each does its own `pythoncom.CoInitialize()`), processing its bucket of claims sequentially against its own session
5. Results are collected off a `Queue` keyed by original claim position, so output order matches input claim order regardless of which worker finished first

### Per-Claim: `_navigate_and_count_drafts(screen, claim_no)`

Up to 3 attempts:
1. `pf9_to_cps520(screen, max_tries=15)` — if it fails, run the VBA's `"i GJBB"`/`"GJBB"` screen-reset recovery trick at `(31,15)`, `send_pf(9)`, retry
2. Place `claim_no @ (8,15)` → ENTER
3. If screen is **CPS515.01** → `send_pf(9)`, retry
4. If screen is **CPS520.01** → claim not found: return message from `GetString(31,2,60)` (or `"CLAIM NOT FOUND"`)
5. Otherwise count drafts: scan rows 6,8,…,18 for non-blank draft numbers; if `"MORE DATA"` at `(20,2,60)` → `send_pf(11)` and keep scanning
6. `send_pf(9)` → return `(True, total_drafts, "")`

### Per-Claim Draft Loop: `_process_line_update_claim(screen, claim_no, lines, settings, ref)`

1. Navigate + count drafts (above); fail fast on error
2. `oop_claim(lines)` — if any line's `NEW_INEL1_AMOUNT < 0` → `"POSSIBLE OUT-OF-NETWORK CLAIM"` *(uses `NEW_INEL1_AMOUNT` rather than the original VBA's hardcoded field index, which drifted out of alignment after a 2026.03.10 column insert — kept as the semantically-correct fix)*
3. Loop `i = 1..total_drafts`:

   **a. Draft selection** — `send_pf(9)` → re-enter claim; page forward with `PF11` once `draft_no > 7` (resets to 1, `pg_cur += 1`)

   **b. Draft open** (skipped if `just_release_claim=Y`):
   | `lst_rls` | Behavior |
   |-----------|----------|
   | `Y` | `ignore_pnd_cd=Y`: read pend code via `rtn_pnd_code`; if it equals `pnd_cd_to_ignore` → skip to next draft; else `place_value(draft_no, 3, 26)`. `ignore_pnd_cd=N`: always `place_value("01", 3, 26)` |
   | `N` | `draft_sub_line_apply01=Y` → `"01"`; else `place_value(draft_no, 3, 26)` |

   ENTER.

   **c. Provider change** (`chg_provider=Y`, skipped if `just_release_claim`): `"X" @ (29,26)` → ENTER → clear `(3,27)` → place `prv_zip @ (5,69)`, `prv_int_nbr @ (7,30)` → ENTER; fail draft if not on CPS310.01

   **d. Screen dispatch** (skipped if `just_release_claim`, screen ID read directly instead):
   | Screen | Claim type | Field entry |
   |--------|-----------|-------------|
   | CPS920.01 | — | ENTER, record `NOT RELEASED.<msg>`, **abort claim** |
   | BLX2460.01 | UB | `remove_prv=Y` → clear `(22,6)`; place `NEW_PRV_VAL @ (22,6)`; `inel2_option="REMOVE INEL2 AMTCD"` → clear rows 12-15 cols 18/30; `rem_oi_elig_amt=Y` → clear rows 18-21 cols 2/14/26; `apply_uc=Y` → `"X" @ (29,71)` |
   | CPS450.01 | HCFA | same shape at `(26,9)` prv, rows 14-17 inel2 clear, rows 20-23 OI clear, UC at `(29,69)` |
   | other | — | `"SCREEN NOT MAPPED."`, abort draft |

   **e. Service-line matching** — unless `skip_no_update_check=Y` and `no_svcln_update()` says every populated line already carries `release_if_inel_code` (then just ENTER through), calls `update_ub_service_lines` / `update_hcfa_service_lines` against the still-unmatched (`_STATUS` unset) lines. On failure: record message, **do not abort the claim** — just skip CPS506 for this draft and continue to the next draft (VBA's `GoTo NextRw` here is commented out; preserved as-is)

   **f. `rTry` loop** (up to 10 iterations) — resolves intermediate screens until CPS506.01:
   - **BLX2460.01 while claim_type=HCFA** (or **CPS450.01 while claim_type=UB**) → wrong screen, navigate back via PF8 + screen-ID field, bypass dup screen if `apply_dpsv≠N`, ENTER, retry
   - **BLX2460.01 / CPS450.01 error message**: if it contains `"PRIOR TO CND ONSET"` and `change_cond_onset_dt=Y` → PF8 to CPS910, place `new_cond_onset_dt @ (5,24)` (formatted `MMDDYY`), ENTER, retry; otherwise record the message and **abort claim**
   - **CPS445.01** (duplicate-claim screen) → ENTER, re-navigate to the correct 450/460 screen if needed, place `"X"` at `(29,76)` HCFA / `(29,78)` UB, ENTER, retry
   - **CPS506.01** → if payee field shows `"1"` and `settings.payee == "0"` → `"DRAFT:i CANCELLED: CHANGE PAYEE TO 1"`, skip to next draft (no release attempted). Otherwise `data_entry_cps506_line_update()` (below) → ENTER. Still on CPS506 → record error message, **abort claim**; else record `RELEASED:DRAFT:i` / `PENDED:DRAFT:i` (word depends on `lst_rls`) and continue to next draft
   - Anything else → `"SCREEN MAPPING ERROR"`, abort claim
   - Exceeding 10 retries → `"TOO MANY SCREEN RETRIES"`, abort claim

4. `finally`: always `send_pf(9)` to reset to CPS520.01
5. Result status = `" | ".join(status_parts)` if any, else `"DONE."`

---

## `utils.py` — Data Entry & Matching Reference

### `data_entry_cps506_line_update(screen, row, settings)`

| Field | Position | Source |
|-------|----------|--------|
| rls_code | (3,13) | `settings` |
| lst_rls | (3,39) | `settings` |
| pnd_rsn | (3,53) | `settings` |
| pnd_op_id | (4,13) | `settings`, overridden by `row['ROUTE_TO_OPID']` if non-blank |
| flw_up_days | (4,38) | `settings` |
| note | (4,50) | `settings` |
| eob | (5,24) | `settings` |
| ck | (5,31) | `settings` |
| dci | (5,39) | `settings` |
| payee | (7,8) | `settings` |
| eob_note (word-wrapped, 43 chars/line, starting row 16 col 36) | via `place_eob_notes()` | `settings` |

Kept separate from `release_pend_macro`'s `data_entry_in_cps506` — this macro also enters DCI at `(5,39)` and doesn't use release_pend's payee-2/3 sub-fields.

### `update_hcfa_service_lines(screen, lines, settings, hcfa_inelcd, exception_codes)`

For each populated service row (5,7,9,11 on CPS450.01):
1. `apply_inel_cd_exceptions=Y` and the row's current inel code is in `exception_codes` → counts as matched, skip to next row
2. Else the row's current inel code must be in `hcfa_inelcd`, else **fail the whole draft**: `"CCN REJECTED:INELCODE NOT MATCHED"`
3. Find first unmatched line whose `BGN_SV_DT`/`CPT`/`UNITS`/`LINE_CHG_AMT`/`MOD01-03` all match the screen row (blank = don't care, via `is_it_matching`)
4. On match, place `NEW_CHRG_AMT`, `AP`, `NEW_MOD01-03`, inel amount/code per `inel_cd_fld` (`1`/`2`/`BOTH`), `inel2_option="APPLY 001 INELCD2"` override, `PROV_RATE`, `SMB_ADJ_AMT/REASON`, `apply_oi_amt=Y` → `OI_ELIG_AMT`/`OI_PAID_AMT` (+`"B"` for `oi_calc_type="TYPE B"`), `OI_TYPE`, `BU`, `IU`, `NEW_TOS`
5. Mark line `_STATUS="DONE"`

Returns `(False, "FAILED:NO SERVICE LINE LISTED")` if no lines were passed in, `(False, "CCN REJECTED:INELCODE NOT MATCHED")` if lines existed but none matched, else `(True, "")`.

### `update_ub_service_lines(screen, lines, settings, ub_inelcd, exception_codes)`

Same shape as the HCFA version, on rows 6-9 of BLX2460.01. Extras:
- `apply_rp_bypass_precert=Y` → `"RP" @ (2,5)`
- `change_from_to_dates=Y` → sync `FROM (2,63)` / `THRU (2,75)` to `SERV (6,17)` if they differ

### Other helpers

| Function | Purpose |
|----------|---------|
| `is_it_matching(value1, value2)` | Blank `value1` = "don't care", always matches |
| `place_eob_notes(screen, note, start_row=16, col=36)` | Word-wraps note text (max 43 chars/line) down the CPS506 note lines |
| `rtn_pnd_code(screen, ln_no)` | Reads the pend code next to a given draft line number |
| `no_svcln_update(screen, inel_code, claim_type)` | True when every populated service line on the current draft already carries `inel_code` — nothing to update |
| `oop_claim(lines)` | True if any line has `NEW_INEL1_AMOUNT < 0` — possible out-of-network claim |
| `load_line_update_reference(path)` | Loads the reference CSV/XLSX — see Setup section above |

### Screen primitives (imported from `release_pend_macro.utils`, not duplicated)

`get_screen_id`, `pf9_to_cps520`, `place_value`, `remove_value`, `send_enter`, `send_pf`, `wait_ready` — see `release_pend_macro_reference.md` for their definitions.

---

## Draft Loop Result

- **All drafts OK** → `{"CLAIM CONTROL #": claim_no, "MACRO STATUS": "DONE."}`
- **Any recorded event(s)** → `{"CLAIM CONTROL #": claim_no, "MACRO STATUS": "<part> | <part> | …"}`
- **Skipped before processing** → `RULE column is empty` / `RULE '<x>' not found in rule CSV`
- **Exception during processing** → `EXCEPTION: <type>: <message>`
- `finally` block always calls `send_pf(9)` to reset to CPS520.01

---

## Settings Flags Quick Reference

All flags come from the matching row in `rule_code_ref_path` CSV (matched by `rule` column, mirrors `rule_code_ref_template.csv`).

| Flag | Values | Controls |
|------|--------|---------|
| `rls_code` | code | Release code, CPS506 (3,13) |
| `lst_rls` | Y/N | Y=release, N=pend; also selects draft-selection mode (list vs. sub-line) |
| `pnd_rsn` | code | Pend reason, CPS506 (3,53) |
| `pnd_op_id` | code | Pend OPID, CPS506 (4,13) — overridden per-claim by `ROUTE_TO_OPID` if present |
| `flw_up_days` | number | Follow-up days, CPS506 (4,38) |
| `note` | text | CPS506 note, (4,50) |
| `eob` | code | EOB code, CPS506 (5,24) |
| `ck` | code | Check code, CPS506 (5,31) |
| `dci` | code | DCI code, CPS506 (5,39) |
| `payee` | 0/1/2/3 | Payee type, CPS506 (7,8) — draft is cancelled if screen shows `1` but this is `0` |
| `eob_note` | text | Word-wrapped EOB note lines on CPS506 |
| `inel_cd_fld` | 1/2/BOTH | Which ineligibility amount/code field(s) to write on the service line |
| `inel_code_val` | code | Fallback inel code when `NEW_INEL1_CD` is blank |
| `inel2_option` | REMOVE INEL2 AMTCD / APPLY 001 INELCD2 | Extra inel2 handling |
| `remove_prv` | Y/N | Clear provider field before placing `NEW_PRV_VAL` |
| `apply_uc` | Y/N | Place `"X"` in the UC field (450/460) |
| `apply_dpsv` | Y/N (default Y unless `"N"`) | Auto-bypass CPS445 duplicate-claim screen |
| `new_pos` | code | New POS placed on HCFA service header |
| `chg_provider` | Y/N | Run the CPS310 provider-change sub-flow before service-line entry |
| `prv_int_nbr` / `prv_zip` | value | Provider internal #/ZIP for `chg_provider` flow |
| `apply_oi_amt` | Y/N | Place `OI_ELIG_AMT`/`OI_PAID_AMT` on the matched line |
| `oi_calc_type` | TYPE B | When set, also places `"B"` in the OI type field |
| `release_if_inel_code` | code | Inel code checked by `no_svcln_update` to skip service-line updates entirely |
| `ignore_pnd_cd` | Y/N | Skip drafts whose pend code matches `pnd_cd_to_ignore` (list-release mode only) |
| `pnd_cd_to_ignore` | code | Pend code to skip when `ignore_pnd_cd=Y` |
| `draft_sub_line_apply01` | Y/N | In sequential mode, always open sub-line `"01"` instead of incrementing |
| `change_from_to_dates` | Y/N | Sync UB FROM/THRU dates to SERV date |
| `apply_rp_bypass_precert` | Y/N | Place `"RP"` on UB service header |
| `rem_oi_elig_amt` | Y/N | Clear existing OI eligibility/paid fields before entry |
| `change_cond_onset_dt` | Y/N | On "PRIOR TO CND ONSET" error, update condition onset date via CPS910 |
| `new_cond_onset_dt` | date | Date placed when `change_cond_onset_dt=Y` (formatted `MMDDYY`) |
| `apply_inel_cd_exceptions` | Y/N | Treat lines with an inel code in `exception_inel_codes` as auto-matched |
| `just_release_claim` | Y/N | Skip draft-selection, provider-change, and service-line steps entirely — go straight to CPS506 |
| `skip_no_update_check` | Y/N | Bypass the `no_svcln_update` short-circuit and always attempt service-line matching |
| `show_confirmation` | Y/N | No-op in batch mode (was an interactive VBA MsgBox) |

---

## Reference File Columns (`reference_path`)

| Column(s) | Feeds |
|-----------|-------|
| `HCFA_INELCD` | `hcfa_inelcd` — valid inel codes for HCFA line matching |
| `UB_INELCD` | `ub_inelcd` — valid inel codes for UB line matching |
| `EXCEPTION_INEL_CODES` | `exception_inel_codes` — codes exempt from the match check |
| `MRU_INNETWORK_POS` | `mru_innetwork_pos` — in-network POS codes (MRU calc) |
| `MED_CALC_CLAIM_NO`, `MED_CALC_DED_COIN_EOB`, `MED_CALC_NEG_CONTRACTUAL`, `MED_CALC_NONCOV` | `med_calc` table (Medicare OI calc) |
| `MRU_YEAR`, `MRU_STATE`, `MRU_IP_PCT`, `MRU_OUT_PCT` | `mru_calc` table (MRU repricing calc) — percents `>1` are divided by 100 |
