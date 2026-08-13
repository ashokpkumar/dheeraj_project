# New Line Update Release Macro — Input Inventory

Every cell/checkbox/column a user populates in the original workbook (as opposed to cells the macro writes back to, like `colStat`, `colExMsg`, `colDraft`, `colClmTyp`), mapped from all 9 VBA modules + the 4 workbook screenshots. Inputs fall into 5 buckets: the MAIN sheet control panel (one-time settings), CLAIM-level row fields, SERVICE LINE row fields, the MRU REPRICING INFO sheet, and the REFERENCE setup sheet.

---

## 1. MAIN sheet — Control Panel (header settings, not per-row)

| # | Cell/Control | Purpose | Code ref |
|---|---|---|---|
| 1 | `G1` | BGN RW (start row) | `Main.txt` L86, L119 |
| 2 | `G2` | END ROW | same |
| 3 | `B10` | SESSION TYPE (REFLECTION / IBM PCOMM) | `Main.txt` L117 |
| 4 | `E10` | Session name (dynamic dropdown) | `oShared` L70/76 |
| 5 | `E4` | INEL.CD FLD (1 / 2 / BOTH) | `oWauben` L436 |
| 6 | `E5` | INEL CODE VAL (default) | `oWauben` L441 |
| 7 | `E6` | REMOVE PRV (Y/N) | `oWauben` L140,164 |
| 8 | `E7` | APPLY UC (Y/N) | `oWauben` L160,184 |
| 9 | `E8` | APPLY DPSV (Y/N) | `oWauben` L213,235,261,270 |
| 10 | `E9` | NEW POS | `oWauben` L484 |
| 11 | `G4` | RLS CODE | `oWauben` L279 |
| 12 | `G5` | LST RLS (Y/N/R) | `oWauben` L90,280,303 |
| 13 | `G6` | PEND RSN | `oWauben` L281 |
| 14 | `G7` | CLAIM NOTE | `oWauben` L285 |
| 15 | `G8` | EOB NOTE | `oWauben` L290 |
| 16 | `I4` | OPID | `oWauben` L282 |
| 17 | `I5` | FLDUP DAYS | `oWauben` L284 |
| 18 | `K4` | EOB | `oWauben` L286 |
| 19 | `K5` | CK | `oWauben` L287 |
| 20 | `K6` | DCI | `oWauben` L288 |
| 21 | `K7` | PAYEE | `oWauben` L275,289 |
| 22 | `K8` | CHG PROVIDER (Y/N) | `oWauben` L118 |
| 23 | `M7` | PRV INT NBR | `oWauben` L123 |
| 24 | `M8` | PRV ZIP | `oWauben` L122 |
| 25 | `N2` | blank / REMOVE INEL2 AMTCD / APPLY 001 INELCD2 | `oWauben` L144,168,454,541 |
| 26 | `N6` | MEDICARE OI CALC option (e.g. "TYPE B") | `oWauben` L461; `Main.txt` L87 |
| 27 | `O7` | APPLY OI AMT (Y/N) | `oWauben` L458,545 |
| 28 | `P6` | RELEASE-IF-ALL-LINES-INEL-CODE (e.g. 950) | `Main.txt` L119; `oWauben` L191 |
| 29 | `U2` | PND CD to ignore | `oWauben` L92,96 |
| 30 | `U5` | Reprice % to apply | `Main.txt` L59,62 |
| 31 | `Y5` | New Condition Onset Date | `oWauben` L223,245 |
| 32 | `AA5` | Apply Condition Onset Date change (Y/N) | `oWauben` L219,241 |
| 33 | `AA6` | Apply Inel Cd Exceptions (Y/N) | `oWauben` L401,490 |

**Checkboxes (ActiveX/OLEObjects):**

| # | Control | Purpose |
|---|---|---|
| 34 | `chkReprice` | APPLY REPRICED % AND CALCULATE |
| 35 | `chkLineDrft` | DRAFT SUB LINE: Apply 01 (re-pend draft selection) |
| 36 | `chkFrmTo` (`chkBp` sheet var) | CHANGE FROM/TO DATES |
| 37 | `chkIgnorePndCd` | IGNORE THIS PNDCD WHEN RELEASING |
| 38 | `chkRemOiEligAmt` | REM OI ELIG/AMT |
| 39 | `chkBp` | APPLY RP BYPASS PRECERT |
| 40 | `chkJustRelease` | JUST RELEASE CLAIM (ignore macro settings) |
| 41 | `chkNoMatching` | DO NOT UPDATE SERVICE LINES |
| 42 | `chkConfirm` | SHOW CONFIRMATION |

**Subtotal: 42 header/settings inputs** (plus 3 action buttons — RUN MACRO, CALCULATE MED OI, MRU REPRICING CALC — which trigger logic but aren't data inputs themselves).

---

## 2. CLAIM LEVEL INFO — per-row inputs (columns A–F)

| Col | Name | Input? |
|---|---|---|
| A `colCCN1` | CLAIM CONTROL # | ✅ input |
| B `colClmTyp` | CLAIM TYPE | ❌ output (macro-detected) |
| C `colDraft` | DRAFTS | ❌ output |
| D `colExMsg` | EXCEPTION MESSAGE | ❌ output |
| E `colRoute` | ROUTE TO CFR/OPID | ✅ input |
| F `colNwPV` | NEW PRV VAL | ✅ input |

**Subtotal: 3 input columns**

---

## 3. SERVICE LINE INFO — per-row inputs (columns G–AK)

| Col | Name |
|---|---|
| G `colCCN2` | CLAIM CONTROL # |
| H `colBgnSvDt` | BGN SV DT |
| I `colCPT` | CPT |
| J `colLnChgAmt` | LINE CHARGE AMT |
| K `colUnit` | UNITS |
| L `colMod1` | MOD 01 |
| M `colMod2` | MOD 02 |
| N `colMod3` | MOD 03 |
| O `colAP` | AP |
| P `colNwAmt` | NEW INEL1 AMOUNT |
| Q `colNwInel` | NEW INEL1 CD |
| R `colNwAmt2` | NEW INEL2 AMOUNT |
| S `colNwInel2` | NEW INEL2 CD |
| T `colNwMod1` | NEW MOD 01 |
| U `colNwMod2` | NEW MOD 02 |
| V `colNwMod3` | NEW MOD 03 |
| W `colSMBAdjAmt` | SMB ADJ AMT |
| X `colSMBAdjRsn` | SMB ADJ REASON |
| Y `colOIEligAmt` | OI ELIG AMT |
| Z `colOIPdAmt` | OI PAID AMT |
| AA `colOIType` | OI TYPE |
| AB `colBU` | BU |
| AC `colIU` | IU |
| AD `colOC` | OC |
| AE `colProvRt` | PROV RATE |
| AF `colNewBgn` | NEW BGN |
| AG `colNewEnd` | NEW END |
| AH `colNewTOS` | NEW TOS |
| AI `colNewChrgAmt` | NEW CHARGE AMT |
| AJ `colBNQty` | BN QTY |
| AK `colBNAmt` | BN AMT |

(`AL colStat` = MACRO STATUS is output-only, excluded.)

**Subtotal: 30 input columns** (OI ELIG/PAID `Y`,`Z` are auto-calculated when `O7="Y"` + Type B, but remain manual-entry fields otherwise — counted once).

---

## 4. MRU REPRICING INFO sheet (MR) — 10 input columns

`mrCCN`(A) CLAIM CONTROL#, `mrBGN`(B) BGN SV DT, `mrCPT`(C) CPT, `mrAMT`(D) LINE CHARGE AMT, `mrUNT`(E) UNITS, `mrMD1`(F) MOD01, `mrMD2`(G) MOD02, `mrMD3`(H) MOD03, `mrPOS`(I) POS, `mrPRV`(J) PRV CITY.

**Subtotal: 10 input columns**

---

## 5. REFERENCE sheet (RF) — setup/reference data

| Col | Purpose |
|---|---|
| A | HCFA INELCD list |
| B | UB INELCD list |
| D | MED CALC – Claim No |
| E | Medicare Deductible & Coin EOB Amt |
| F | Negative Contractual Amt |
| G | Non-Covered Amt |
| J | MRU year |
| K | State |
| L | IP % |
| M | OUT % |
| N | In-network POS list |
| P | Exception Inel Codes (no-update list) |

(`H TOTAL` is a formula/output, excluded.)

**Subtotal: 12 input columns**

---

## Grand Total

| Category | Count |
|---|---|
| MAIN sheet control-panel cells | 33 |
| MAIN sheet checkboxes | 9 |
| CLAIM LEVEL row columns | 3 |
| SERVICE LINE row columns | 30 |
| MRU REPRICING INFO columns | 10 |
| REFERENCE setup columns | 12 |
| **Total distinct input fields** | **97** |

**Notes / caveats:**
- Action buttons (RUN MACRO, CALCULATE MED OI, MRU REPRICING CALC) and the 3 tab-clear labels aren't counted — they're triggers, not data inputs.
- `CALCULATE_UHSS_REPRICED_AMTS` in `oShared` references an `SL` sheet that isn't in this workbook's file tree — it looks like leftover shared-module code not active in this macro's flow, so it's excluded from the count.
- `MN.Range("F3")` is checked in `CURRENT_SESSION` but not visible in the screenshots — possibly a legacy/hidden field; flagged but not counted separately since its role is unclear.
- Per-row columns (Categories 3–4) are counted once as *field types*, not multiplied by number of claim/service-line rows.

---

## Mapping to the Python port

For cross-reference against `new_line_update_release_macro_reference.md`:

| Original bucket | Where it landed in the port |
|---|---|
| MAIN sheet control panel (42 items) | `rule_code_ref_template.csv` settings columns, selected per claim via `RULE` |
| CLAIM LEVEL row fields (3 cols) | `context['df']` claim-level columns (`CLAIM_NO`, `ROUTE_TO_OPID`, `NEW_PRV_VAL`) |
| SERVICE LINE row fields (30 cols) | `context['df']` service-line columns |
| MRU REPRICING INFO sheet (10 cols) | `mru_info_path` file, read by `new_line_update_mru_repricing_calc` |
| REFERENCE sheet (12 cols) | `reference_path` file, read by `load_line_update_reference()` |
