# Release Pend Macro — Functional Reference

## File Overview

| File | Role |
|------|------|
| `script.py` | Main orchestrator — `release_pend_run_batch()` loop, rule CSV loading, per-claim/per-draft logic |
| `utils.py` | Screen primitives (`place_value`, `send_pf`, etc.) + all shared helper functions |
| `tod.py` | TOD (Type of Diagnosis) update logic |
| `hcfa.py` | HCFA claim data entry on CPS450.01 |
| `ub.py` | UB claim data entry on BLX2460.01 |

---

## Call Order in `release_pend_run_batch`

### 1. Setup (runs once)

| Function | File | What it does |
|----------|------|--------------|
| `_load_rule_code_ref(path)` | `script.py` | Reads rule CSV → `{RULE_UPPER: {col: val, …}}` |
| `load_code_refs(xlsx_path)` | `utils.py` | Reads DX code ref Excel → named code dicts (see below) |
| `win32com.client.Dispatch("EXTRA.System")` | `script.py` | Connects to EXTRA emulator |

**Code dicts returned by `load_code_refs`:**

| Key | Excel Column | Purpose |
|-----|-------------|---------|
| `dx_codes` | A | ICD10-CM DX codes |
| `lab_codes` | B | Lab CPT codes |
| `ub_rev_codes` | C | UB revenue codes |
| `grid_price` | E / F | CPT code → allowed price |
| `rejected_inel` | H | Rejected ineligibility codes |
| `mod_codes` | J | Modifier codes |
| `dny_by_cpt` | K | CPT denial codes |
| `dnl_inel_exceptions` | N | Denial inel exceptions |
| `ck_inel` | P | Check inel codes |
| `apply_disc_after_dnl` | R | Apply discount after denial codes |
| `rem_disc_amt` | T | Remove discount amount inel codes |
| `possible_hcr` | V | Possible HCR CPT codes |
| `cpt_codes_full_pd` | X | CPT codes for full-paid validation |
| `lab_cpt_codes_by_rule` | sheet: `lab_cpt_codes` | Per-rule lab CPT codes |

---

### 2. Per-Claim Pre-Flight (script.py inline)

| Check | Condition | Outcome |
|-------|-----------|---------|
| RULE in rule CSV? | `rule_key not in rule_ref` | SKIP: "RULE not found in rule CSV" |
| Seq-order skip | `seq_ordr=Y` AND `cert_no == cert_no_skip` | `send_pf(9)` → SKIP: "SKIPPED (SEQ ORDER)" |
| TOD update | `aply_tod_updt=Y` | Call `tod.py: tod_update()` — see below |

---

### 3. TOD Update (`tod.py`)

**`check_tod(row)`** — validates `row['TOD']`: must be numeric, 1-2 digits.

**`tod_update(screen, row, settings)`** — called when `aply_tod_updt=Y`:

1. Navigate to **CPS520.01**: place `claim_no @ (8,15)`, clear `(9,15)`, `(12,15)`, ENTER
2. `place_value("01", 3, 26)` → ENTER → `place_value("X", 29, 9)` → ENTER (open condition list)
3. Loop pages of conditions:
   - For each condition where TOD = `"99"` or `"00"`:
     - Place `rcn @ (2,18)`, `"X" @ (29,55)` → ENTER → **CPS910.01**
     - `place_value(TOD.zfill(2), 5, 60)` → ENTER
     - If still on CPS910 → return `False` (fail)
     - Navigate back to condition list: `send_pf(8)` → `"850" @ (2,37)` → ENTER → `"X" @ (29,9)` → ENTER
4. Returns `True` on success, `False` on failure

---

### 4. CPS520.01 — Claim Entry (utils.py primitives)

```
place_value(claim_no, 8, 15)
remove_value(9, 15)
remove_value(12, 15)
send_enter()
```

If still on CPS520 after ENTER: read error from `GetString(31, 2, 70)` → SKIP.

**`get_screen_id(screen)`** reads `GetString(1, 2, 11)` to identify which screen is active.

---

### 5. Draft Selection (script.py)

| Mode | Flag | Logic |
|------|------|-------|
| List-release | `lst_rls=Y` | Scan rows 6,8,10,12,14,16,18 — find first where `GetString(row, 6, 2) ≠ "66"` → `place_value(row#, 3, 26)` |
| Sequential | `lst_rls=N` | `place_value(j, 3, 26)` where `j` starts at 1 and increments; resets to 1 at draft 8+ (also sends `send_pf(11)` first) |

Then `send_enter()` to open the draft.

---

### 6. CPS850.01 — Claim Header (utils.py + script.py)

Only executed when the screen after draft selection is CPS850.01.

| Flag | Action | Function / Position |
|------|--------|-------------------|
| `aply_opi=Y` | Place `NEW_OPI @ (22,58)`; `"x" @ (23,52)`; ENTER; if still 850 → FAIL; PF8 → `"850" @ (2,37)` → ENTER | `place_value` / `send_enter` / `send_pf` |
| `aply_opi=D` | Clear `(22,58)`; `"x" @ (23,52)`; ENTER | `remove_value` |
| `aply_850_nt = APPEND / 2ND LINE` | Word-wrap `NOTE_850` onto BLX120.01 (CSR note screen) | `utils.py: place_new_csr_note(screen, row, opt)` |
| `chnge_dx_cd=Y` | `DX_CD @ (23,6)`; `"Y" @ (23,14)` | `place_value` |
| `aply_int_zip=Y` | `"X" @ (29,26)` → ENTER → **CPS325.01**: `ZIP @ (5,69)`, `INT_NO @ (7,30)` → ENTER | `place_value` / `send_enter` |

**`place_new_csr_note(screen, row, opt)`** (`utils.py`):
- `place_value("x", 29, 21)` → ENTER → navigate to BLX120.01
- `APPEND`: reads existing note at (6,11) + (7,11), appends `NOTE_850`
- `2ND LINE`: writes `NOTE_850` to row 7
- Word-wraps at 60 chars, then ENTER → PF8 → `"850" @ (2,37)` → ENTER (return to CPS850)

---

### 7. CPS910.01 — TOD Prompt During Draft (utils.py)

Only executed when screen after CPS850 ENTER is CPS910.01.

```python
place_value(TOD.zfill(2), 5, 60)
send_enter()
# if still on CPS910.01 → FAIL draft
```

---

### 8. Condition Updates (utils.py)

**`add_condition_note(screen, row)`** — if `aply_cond_nt=Y`:
1. `send_pf(8)` → `place_value("910", 2, 37)` → `send_enter()`
2. `place_value(COND_NOTE, 7, 6)` → `send_enter()`
3. If still on CPS910.01 → return `False` (fail)

**`update_condition_afv(screen, row)`** — if `aply_cond_afv=Y`:
1. `send_pf(8)` → `place_value("910", 2, 37)` → `send_enter()`
2. `place_value(AFV, 5, 68)` → `send_enter()`
3. If still on CPS910.01 → return `False` (fail)

---

### 9. HCFA Data Entry (`hcfa.py` + `utils.py`)

**Screen: CPS450.01**

**`apply_ineligibility_codes("HCFA", …)`** (`utils.py`) runs first:
- For service rows 5, 7, 9, 11: if CPT in `dny_by_cpt` → place ineligibility code on the corresponding inel rows
- `send_enter()` → PF8 → `"450" @ (2,37)` → ENTER

**`hcfa_data_entry(screen, row, settings, codes, status_parts)`** (`hcfa.py`):

| Step | Action |
|------|--------|
| NEW_POS | `PutString(NEW_POS, 2, 6)` |
| apply_uc=Y | `PutString("X", 29, 69)` |
| Per service line (5,7,9,11) | inel codes, AP codes, denial codes, modifiers, grid price, DX codes, OI elig/pd |
| `aply_631_inel=Y` | `apply_631_inel(screen, "HCFA", "631")` (`utils.py`) |
| `aply_034_inel=Y` | `apply_631_inel(screen, "HCFA", "034")` (`utils.py`) |
| `remove_prv=Y` | `remove_value(26, 9)` |
| NEW_PRV_CD | `place_value(NEW_PRV_CD, 26, 9)` |
| ENTER | Submit CPS450 |
| CPS445.01 dup screen | `send_enter()` → `"x" @ (29,76)` → ENTER (bypass); or `return 0` if `aply_dpsv=N` |
| TOS/POS errors | `hcfa_tos_entry()` — fixes TOS at service-line level |
| Surprise bill | If PRV code in E/G/Y → change to `"}"` |
| CPS506.01 checks | Payee check, `vld_amt_pd`, `amt_858_inq`, `chk_inel`, two-AP-code entry |
| `data_entry_in_cps506()` | See Section 11 |
| Returns | `1` = success (continue); `0` = FAIL draft |

**Sub-functions called by `hcfa_data_entry`:**

| Function | File | When |
|----------|------|------|
| `hcfa_tos_entry()` | `hcfa.py` | POS/TOS edit errors |
| `bypass_duplicate()` | `utils.py` | `aply_631_inel` or `aply_034_inel=Y` |
| `check_inel_code()` | `utils.py` | `chk_inel=Y` — checks CPS408 for inel codes |
| `is_fully_paid()` | `utils.py` | `vld_amt_pd=Y` or `vld_amt_pd_by_cpt=Y` |
| `total_amt_858()` | `utils.py` | `amt_858_inq=Y` — sums 858 inel from CPS408 |
| `plan_id_update()` | `utils.py` | `updt_hic=Y` — updates plan ID on member record |
| `collect_inel_700()` | `utils.py` | `updt_oc_for_700=Y` — reads 700 inel from CPS408 |
| `apply_discount_after_switch()` | `utils.py` | `flip_mod=Y` + `apply_disc_aft_flip=Y` |

---

### 10. UB Data Entry (`ub.py` + `utils.py`)

**Screen: BLX2460.01**

**Date sync** (`updt_frm_to_dt=Y`, `script.py`):
- Read `FROM @ (2,63)`, `THRU @ (2,75)`, `SERV @ (6,17)`
- FROM ≠ SERV → `remove_value(2,63)`; `place_value(SERV, 2,63)`
- THRU ≠ SERV → `remove_value(2,75)`; `place_value(SERV, 2,75)`

**`apply_ineligibility_codes("UB", …)`** (`utils.py`):
- For rows 6-9: if CPT in `dny_by_cpt` → place inel code on inel rows
- `send_enter()` → PF8 → `"460" @ (2,37)` → ENTER

**`ub_per_diem_process(screen, row, settings)`** (`ub.py`) — if `chk_per_diem=Y`:
- Navigates through CPS506 with hard-coded per-diem values: `rls_code=60`, `pnd_rsn=O99`, `pnd_opid=CF10`, `note="PER DIEM LINE"`
- On BLX2460.01: places `NEW_POS @ (1,26)`, `NEW_TOS @ (6,14)`, `T_BILL @ (6,40)`, `T_DISC @ (12,2)`, `NEW_INEL_CD @ (12,14)`
- **Stops all remaining drafts for this claim** → status: "PER DIEM PROCESSED"

**`ub_data_entry(screen, row, settings, codes, status_parts)`** (`ub.py`):

| Step | Action |
|------|--------|
| NEW_POS | `PutString(NEW_POS, 1, 26)` |
| apply_uc=Y | `PutString("X", 29, 71)` |
| Per service line (rows 6-9) | inel codes, AP codes, denial codes, BN codes, OI elig/pd |
| `aply_631_inel=Y` | `apply_631_inel(screen, "UB", "631")` |
| NEW_PRV_CD | `PutString(NEW_PRV_CD, 22, 6)` |
| ENTER | Submit BLX2460 |
| Edit errors | 8803/8806/8807 → place `"RP" @ (2,5)`, clear `(2,12)`, ENTER |
| 1237-SP REQUIRED | Calculate SP amount per SAD line, place, ENTER |
| TOS edits | `ub_tos_entry()` — fixes TOS at service-line level |
| `data_entry_in_cps506()` | See Section 11 |
| Returns | `1` = success; `0` = FAIL draft |

**Sub-functions called by `ub_data_entry`:**

| Function | File | When |
|----------|------|------|
| `ub_tos_entry()` | `ub.py` | TOS/POS edit errors |
| `bypass_duplicate()` | `utils.py` | `aply_631_inel` or `aply_034_inel=Y` |
| `check_inel_code()` | `utils.py` | `chk_inel=Y` |
| `is_fully_paid()` | `utils.py` | `vld_amt_pd=Y` or `vld_amt_pd_by_cpt=Y` |
| `total_amt_858()` | `utils.py` | `amt_858_inq=Y` |
| `plan_id_update()` | `utils.py` | `updtHic=Y` |
| `collect_inel_700()` | `utils.py` | `updt_oc_for_700=Y` |

---

### 11. CPS506.01 — Release / Pend Screen (`utils.py`)

Called from inside both `hcfa_data_entry` and `ub_data_entry`.

**`data_entry_in_cps506(screen, row, settings)`**:

| Field | Screen Position | Value Source |
|-------|----------------|--------------|
| rls_code | (3, 13) | `settings` |
| lst_rls | (3, 39) | `settings` |
| pnd_rsn | (3, 53) | `settings` |
| pnd_opid | (4, 13) | `settings` |
| flwup_days | (4, 38) | `settings` |
| note | (4, 50) | `settings` |
| disti_unit | (5, 13) | `settings` |
| eob | (5, 24) | `settings` |
| ck | (5, 31) | `settings` |
| EOB notes (word-wrapped) | (16+, 36) | `row['EOB_PER_CLM']` overrides `settings['eob_note']` |
| payee | (7, 8) | `settings` |
| PROV_NAME (payee=2) | (10, 18) | `row` — max 28 chars |
| PROV_ADD (payee=2) | (11–12, 18) | `row` — max 76 chars |
| CITY / STATE / ZIP2 (payee=2) | (13, 18/43/52) | `row` |
| SPLIT_EE / SPLIT_PR (payee=3) | (9, 22) / (9, 41) | `row` |

After `send_enter()`, check `GetString(1, 74, 3)`:
- `"112"` → Released successfully
- `"115"` → Error — record message
- `"114"` → Duplicate claim

Auto-handled errors after ENTER (in both `hcfa_data_entry` / `ub_data_entry`):
- `CRL 37 PROMPT PAY` → place `"R" @ (3,39)` → ENTER
- `CRL 36 DENIAL RELEASE CODE REQUIRED` → `"71" @ (3,13)`, `"Y" @ (3,39)` → ENTER
- `CRL 95 DUPLICATE INEL CODES` → navigate back to 450/460, clear `908` inel codes, re-enter CPS506

---

### 12. Draft Loop Result (script.py)

- **All drafts OK** → `{"CLAIM CONTROL #": claim_no, "MACRO STATUS": "DONE."}`
- **Draft failed** → `{"CLAIM CONTROL #": claim_no, "MACRO STATUS": <error_msg>}`
- `finally` block always calls `send_pf(9)` to reset to CPS520.01

---

## Utils.py Screen Primitive Reference

| Function | Signature | What it does |
|----------|-----------|-------------|
| `wait_ready` | `(screen)` | Polls `screen.OIA.XStatus` until 0 (emulator idle) |
| `get_screen_id` | `(screen) → str` | `GetString(1, 2, 11)` — returns screen ID like `"CPS520.01"` |
| `place_value` | `(screen, val, r, c)` | MoveTo → EraseEOF → PutString at row r, col c; skips empty values |
| `remove_value` | `(screen, r, c)` | MoveTo → EraseEOF at row r, col c |
| `send_enter` | `(screen)` | `SendKeys("<Enter>")` + `wait_ready()` |
| `send_pf` | `(screen, n)` | `SendKeys("<PFn>")` + `wait_ready()` |
| `pf9_to_cps520` | `(screen, max_tries=15) → bool` | Loops PF9 until on CPS520.01 |

---

## Settings Flags Quick Reference

All flags come from the matching row in `rule_code_ref_path` CSV (matched by `RULE` column).

| Flag | Values | Controls |
|------|--------|---------|
| `seq_ordr` | Y/N | Skip if cert_no repeats (seq-order protection) |
| `aply_tod_updt` | Y/N | Run TOD update before draft loop |
| `lst_rls` | Y/N | Draft selection mode (Y=list, N=sequential) |
| `aply_opi` | Y/D/N | OPI field on CPS850: Y=place, D=delete |
| `aply_850_nt` | APPEND / 2ND LINE / DO NOT APPLY NOTE | CSR note on BLX120 |
| `chnge_dx_cd` | Y/N | Change DX code on CPS850 |
| `aply_int_zip` | Y/N | Update INT/ZIP on CPS325.01 |
| `aply_cond_nt` | Y/N | Add condition note via CPS910 |
| `aply_cond_afv` | Y/N | Update AFV via CPS910 |
| `updt_frm_to_dt` | Y/N | Sync FROM/THRU dates to service date (UB only) |
| `chk_per_diem` | Y/N | Run per-diem process instead of normal UB entry |
| `deny_clm` | Y/N | Apply denial code instead of release |
| `denial_code` | code | Denial inel code to apply |
| `inel_code` | code | Ineligibility code for dny_by_cpt lines |
| `apply_001` | 1 ONLY / ALL LINES / N/A | Apply/overwrite inel code 001 |
| `remove_inel_amt_cd` | INEL/CD1 / INEL/CD2 / INEL/CD ALL / SPECIFIC / N/A | Remove inel amounts and codes |
| `aply_631_inel` | Y/N | Apply inel code 631 and bypass dup screen |
| `aply_034_inel` | Y/N | Apply inel code 034 and bypass dup screen |
| `vld_amt_pd` | Y/N | Validate claim is 100% paid before releasing |
| `chk_inel` | Y/N | Check for specific inel codes on CPS408 before releasing |
| `amt_858_inq` | Y/N | Sum 858 inel amounts (inquiry mode — no release) |
| `aply_dpsv` | Y/N | Auto-bypass duplicate claim screen (CPS445) |
| `payee` | 0/1/2/3 | Payee type on CPS506 |
| `new_ap_cd` | code | AP code to seed into claim row from rule CSV |
| `new_prv_cd` | code | Provider code to seed into claim row from rule CSV |
