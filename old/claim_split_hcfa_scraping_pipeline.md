# Claim Split HCFA — the scraping pipeline (after sign-in)

Companion to `claim_split_hcfa_webclaims_auth_flow.md`, which covers only
sign-in. This one picks up from "we have an authenticated session (or don't
need one)" through to the CSV files landing on disk: searching for the
claim, downloading its PDF, parsing every box out of it, and how
`script.py` drives all of that per claim. Each step is tagged with the
Python file:line and the VBA file it ports, so it can be checked side by
side.

Two independent retrieval paths feed the same PDF-parsing pipeline,
selected by `use_new_api` (`chkWbClaim` in the VBA):

- **New API path** — `WebClaimsSession.fetch_claim()`, ports
  `NEW_WEBLCLAIM` (`oWebClaim.txt`). Needs the sign-in handshake (see the
  companion doc).
- **Legacy path** — `get_pdf_claim_legacy()`, ports `Get_PDF_Claim2`
  (`oWebClaim.txt`). No sign-in handshake at all — a bare form POST.

Both end up handing a local PDF path to the same extraction code
(`pdf_extract.py`).

## A. New API path — search and download (post sign-in)

Picks up right where the auth doc leaves off, once `self.authenticated`
is `True`.

**A1. POST to `/Search`** (`web_claims.py:351-354` or `:422-425`
depending on which branch got there) = VBA's
`.Open "POST", wURL_SEARCH, False ... .send wPRM` (`oWebClaim.txt:60-61`
or `:70`). Same JSON payload built in setup (see companion doc, step 1).

**A2. Empty-result check** (`web_claims.py:447-451`) = VBA
`If rE <> "{""Authorized"":[],""Unauthorized"":[]}" Then ... Else: GoTo
JUSTEXIT` (`oWebClaim.txt:78-90`). An empty result here becomes
`"PDF Claim not found."` with no PDF path.

**A3. Parse `ROWID` / `CLAIMTYPE` / `ERRORMSG`** — `_parse_search_result()`
(`web_claims.py:473-491`) = VBA's manual string-splitting around
`"Unauthorized":` and per-field `Select Case` (`oWebClaim.txt:80-110`).
**Flagged as the least-verified part of this whole path** — it's a regex
approximation (`re.findall(r'"([A-Za-z]+)"\s*:\s*"?([^",}]*)"?', body)`)
of VBA's hand-rolled slicing, never checked against a real response body.
If claims keep coming back "not found" even after sign-in succeeds, this
is the first place to look — add a raw response body dump and compare its
actual JSON shape against what this regex expects.

**A4. Error / not-found short-circuit** (`web_claims.py:457-460`) = VBA
`If ErMSG <> "NULL" Then NEW_WEBLCLAIM = ErMSG` (`oWebClaim.txt:112-113`).

**A5. Download the PDF** (`web_claims.py:462-464`) = VBA
`DownloadFile wURL_GENPDF & "rowid=" & ROWID & "&ccn=" & CCN, ...`
(`oWebClaim.txt:116`). `download_file()` (`web_claims.py:108-121`) mirrors
VBA's `DownloadFile`/`URLDownloadToFile` (`oWebClaim.txt:230-234`) as a
streamed `requests` GET instead of the Win32 API call.

Returns `(claim_type, local_pdf_path)` either way — this is the tuple
`script.py` receives.

## B. Legacy path — no sign-in needed at all

**B1. POST the search form** (`web_claims.py:152-156`) = VBA
`.Open "POST", webURL, False ... .send webParam` (`oWebClaim.txt:141-144`,
`Get_PDF_Claim2`). Straight form POST to
`umrwebclaims.optum.com/webclaims/index.php` — a completely different
host from the New API path, and no auth handshake of any kind; this is
why the whole SSO investigation in the companion doc doesn't apply here.

**B2. "Not found" check** (`web_claims.py:160-162`) = VBA's loop over
`<b>` tags for `"Some CCN search criteria did not yield a result:"`
(`oWebClaim.txt:148-152`), via BeautifulSoup instead of
`htmlDoc.getElementsByTagName("b")`.

**B3. Walk the results table, build each row's PDF link, download**
(`web_claims.py:164-190`) = VBA's `For tblRw = 1 To ... Step 2` loop over
`tblElem(2).Rows` reading `input` elements 6 apart (`cntPlcr`) to build
`btnClicktoView`/`OrgSearchSeq`, then `DownloadFile` per match
(`oWebClaim.txt:154-167`). The name-mangling (`%2f`/`%2b` substitution,
stripping `"submit_"`) and the `cnt_placer += 6` stride are kept exactly
as VBA does them — this is scraping a specific HTML table's hidden input
naming scheme, not a documented API, so any layout change on the legacy
page breaks this the same way it'd break the VBA.

**B4. Claim type from column 8** (`web_claims.py:186-187`) = VBA
`Trim(tblElem(2).Rows(tblRw).Cells(7).innerText)` (`oWebClaim.txt:164`) —
0-indexed `cells[7]` in Python vs VBA's `Cells(7)`, which is also
effectively the 8th `<td>` (VBA's `Cells` collection here is 0-based in
this specific HTML-table-object usage, same index either way).

**Not ported**: `Get_PDF_Claim` (`oWebClaim.txt:172-228`), the oldest
IE-automation fallback, already superseded by `Get_PDF_Claim2` in the VBA
itself before this port started.

## C. PDF extraction — `pdf_extract.py` vs `oReadPdf.txt`

Both paths above hand a local PDF path to `extract_claim()`
(`pdf_extract.py:483-517`), the single entry point `script.py` calls per
claim. It mirrors the sequence `cmdRun_Click` runs per claim during
"02.GET EDI DETAILS":

**C1. Demographics** — `extract_demographics()` (`pdf_extract.py:79-157`)
= `CLAIM_DEMOGRAPHICS_INFORMATION` (`oReadPdf.txt:317-377`). Box-by-box
HCFA-1500 page-1 extraction — same `(left, bottom, right, top)`
coordinates as the VBA for every field (Box 1 Insured ID, Box 2 Patient
Name, ... Box 33 Billing Provider). Two things worth checking against a
real PDF, both already flagged inline:
  - **Box 17a/17b** (`pdf_extract.py:110-111`) are read from the *exact
    same coordinates* — this matches the VBA (`oReadPdf.txt:346-347`
    also uses identical coordinates for both), so it's a faithful port of
    what's very likely a pre-existing VBA bug, not a new one.
  - Address parsing (`reformat_address()`, `pdf_extract.py:46-72`) mirrors
    `Reformat_Address` (`oReadPdf.txt:379-425`) with one regex instead of
    VBA's `InStr`/`Mid` chain — should be equivalent for well-formed
    "City, ST Zip" input, but wasn't tested against a real Box 32/33
    value with irregular formatting.

**C2. Service lines** — `extract_service_lines()`
(`pdf_extract.py:170-223`) = `CLAIM_SERVICELINES_INFORMATION`
(`oReadPdf.txt:2-47`). Scans every page for the `"HEALTH INSURANCE CLAIM
FORM"` marker, reads up to 6 lines per matching page, same box
coordinates stepping down by 25 points per line (`bottom -= 25`). Keeps
VBA's unusual stop condition exactly: the moment a line's "Date of
Service From" box comes back empty, extraction stops for the **whole
PDF**, not just the current page (`pdf_extract.py:190-191`, matching
`GoTo JUSTEXIT` jumping clear of both loops at `oReadPdf.txt:14`/`46`) —
worth being aware of if a PDF ever has a genuinely blank line partway
through a page followed by more real lines after it; both VBA and this
port would silently drop everything past that blank line.

**C3. Medicare/Medicaid COB per line** —
`extract_medicare_cob_line()` (`pdf_extract.py:226-253`) =
`Medicare_Cob_Information` (`oReadPdf.txt:49-70`), called once per line
from inside C2 (`pdf_extract.py:217`) same as the VBA calls it from
inside its own per-line loop (`oReadPdf.txt:39`). Flagged in both places
as fragile: assumes exactly one match per `TextCoordinates()` call
(`oReadPdf.txt:55-57` splits on `,` directly without handling multiple
`|`-joined matches; `pdf_extract.py:238-240` does the same).

**C4. Repricing info** — `extract_repricing_info()`
(`pdf_extract.py:260-370`) = `CLAIM_REPRICING_INFORMATION`
(`oReadPdf.txt:146-315`). This is **the highest-risk piece of the whole
port**, flagged in both the module docstring (`pdf_extract.py:12-17`) and
inline:
  - Only the newer ("ADDED 2025.11.06") `KeyPattern` set is ported —
    `DATE FRM` / `DATE THR` / `CPT/HCPCS` / `CHARGES` / `Allowed/` /
    `Discount/` (`pdf_extract.py:319`), each read with the
    `CDbl(CordSet(1)) - 23.25` / `- 15.25` offset adjustment
    (`pdf_extract.py:331`, matching `oReadPdf.txt:254-255` etc.). The
    **older lowercase set** (`Date Frm` / `HCPCS` / `/Repriced` /
    `/Ineligible`, `oReadPdf.txt:245-250`, `275-294`) used when
    `chkWbClaim` is unchecked — i.e. the **legacy PDF path (B above)** —
    was **not ported**. If a claim fetched via `get_pdf_claim_legacy()`
    comes back with `REPRICE_*`/`ALLOWED_REPRICED`/`DISCOUNT_*` fields
    blank on the service lines, this is why.
  - `HIC_MEM_NO` extraction from the COB table (`pdf_extract.py:282-303`)
    = VBA's `n = topTble(3) To bottomTble(1) Step -13` loop
    (`oReadPdf.txt:175-182`) — same row-walking-by-13-points logic.
  - Labeled single-value fields (Re-Price Ind, Timely Filing, Claim NTE,
    Re-Priced By, Method) via `_read_labeled_field()`
    (`pdf_extract.py:373-383`) = the repeated
    `olCoordinates = .TextCoordinates(...) / olSet = Split(...) /
    .ReadPage(...)` pattern (`oReadPdf.txt:189-229`) — collapsed into one
    helper instead of five near-identical blocks. **Not ported**: VBA's
    `chkWbClaim`-dependent index selection for the "Method" field
    specifically (`oReadPdf.txt:222-226`, `iDx = UBound(...) - 1` when
    not using the web claim checkbox, else `iDx = 0`) — this Python port
    always behaves like the `chkWbClaim = True` case (`iDx = 0`, i.e.
    always the *first* match), which is only correct for the New API
    path. If Method info comes back wrong specifically on legacy-path
    claims, this index selection is why.

**C5. Claim-level COB figures** — `extract_medicare_medicaid_cob()`
(`pdf_extract.py:403-463`) = `Medicare_Medicaid_Cob_Information`
(`oReadPdf.txt:72-144`). Same label list (Deductible, Coinsurance,
Calculated Approved Amount, Paid, Patient Responsibility, Non-Covered,
Contractual, Medicare ID, Other Insurance Type —
`_COB_KEY_FIELDS`, `pdf_extract.py:390-400` vs `KeyPattern(0..8)`,
`oReadPdf.txt:76-84`). One label VBA has that this port doesn't:
**`"HIC Number"`** (`oReadPdf.txt:110`, `Case "HIC Number":
INF.Range("CA"...)`) — already flagged elsewhere in this codebase's
`IO_Reference.html` as dead code in the VBA itself, since VBA's own
`Select Case` only ever matches on the *actual* searched pattern
`"Medicare ID"`, never `"HIC Number"` (that case label can never fire in
VBA either) — so not porting it is intentional, not an oversight.
  - The adjustment-detail table walk (`pdf_extract.py:433-462`) = VBA's
    `SEQ) GRP CD, ADJ RSN: AMT` section walk (`oReadPdf.txt:115-140`) —
    both flagged as one of the more fragile bits of the macro; the
    header-vs-line-item disambiguation (`"LINE#" in header_text` /
    `InStr(..., "LINE#")`) and the `12.44`-point / `9`-and-`8`-point row
    steps are kept exactly as VBA has them.

**C6. Roll-up and Dx-pointer resolution** — back in `extract_claim()`
(`pdf_extract.py:494-515`):
  - Total charges summed across service lines (`pdf_extract.py:494-500`)
    = VBA's running `TotalCharges = TotalCharges + SVL.Range("L" &
    rW)` inside the service-line loop plus
    `INF.Range("BI" & x) = Format(TotalCharges, "0.00")` in
    `cmdRun_Click` (`Main.txt:69`) — done as a separate pass here instead
    of accumulating during C2, same end result.
  - `resolve_dx_code()` (`pdf_extract.py:470-480`) = the diagnosis-pointer
    lookup VBA does in `POPULATE_MAIN_SHEET` (`LEFT(RC[-3],1)` reduction
    against Box 21 A–L) — ported here as a claim-info lookup per service
    line instead, so it's available on `service_lines_df` directly rather
    than needing a separate MAIN-sheet population pass.

## D. The PDF reader backend — `pdf_backend.py`

Not a VBA port at all — it's a **replacement** for a proprietary COM
component (`PdfClaimImageDetails.dll`) the VBA uses for its
`.TotalPages()` / `.TextCoordinates()` / `.ReadPage()` calls
(`pdf_backend.py:1-17`). Since that DLL's source isn't available,
`ClaimPdfReader` re-implements the same three-call interface on top of
`pdfplumber`, so `pdf_extract.py` above could stay a near line-for-line
translation instead of being restructured around a different API shape.

**This is flagged as the single highest-risk file in the whole port**
(`pdf_backend.py:17-34`) — two specific unknowns:
- **Coordinate scale**: VBA's `ReadPage(file, page, LEFT, BOTTOM, RIGHT,
  TOP)` calls assume standard PDF point space (origin bottom-left), which
  `read_page()` converts to pdfplumber's top-down convention using page
  height (`pdf_backend.py:102-122`) — but what DPI/scale the *original*
  DLL's coordinates were calibrated against (screen pixels? PDF points? a
  fixed rendering resolution?) is unknown. If extracted text comes back
  empty or misaligned on a real PDF, a uniform scale factor is the most
  likely missing piece — the doc note says to add it in this one file,
  not scattered across every call site in `pdf_extract.py`.
- **Match semantics**: `text_coordinates()` does a case-insensitive
  substring search per visual line, joining multiple matches with `"|"`
  (`pdf_backend.py:75-97`) — mirrors how VBA does
  `Split(TextCoordinates(...), "|")`, but the original DLL's exact
  matching rules (word-boundary? multi-line labels?) are unverified.

## E. Orchestration — `script.py`'s per-claim loop

`claim_split_get_edi_details()` (`script.py:94-206`) is what actually
drives A/B and C/D above, once per row in `context['df']`:

**E1. Length gate** (`script.py:154-157`) = VBA's
`If Len(CCN) <> 11 Then GoTo NXTCLAIM` (`Main.txt:55`) — invalid claim
numbers are recorded with `MACRO_STATUS = "INVALID CLAIM NUMBER..."` and
skipped, same as the VBA's per-row skip.

**E2. Path selection** (`script.py:159-162`) = VBA's
`If .chkWbClaim.Value <> True Then tCLAIM = Get_PDF_Claim2(CCN) Else
tCLAIM = NEW_WEBLCLAIM(CCN)` (`Main.txt:56`).

**E3. UB / missing-PDF / success branch** (`script.py:164-181`) = VBA's
`Select Case tCLAIM` (`Main.txt:59-88`): `"UB"` → cancelled with the
"NOT SUPPORTED BY THIS MACRO" message (`Main.txt:60-62`); no PDF → status
carries the underlying error/`"FILE NOT EXISTS"`; otherwise → runs C
above (`CLAIM_DEMOGRAPHICS_INFORMATION` +
`CLAIM_SERVICELINES_INFORMATION` + `CLAIM_REPRICING_INFORMATION`,
`Main.txt:66-70`), then deletes the temp PDF (`script.py:177-181`) = VBA's
`DEL_EXISTING_FILE fnLOC & "\" & CCN & ".pdf"` (`Main.txt:91`).

**E4. Exception safety net** (`script.py:182-185`) — not a VBA construct;
Python-only defensive wrapping so one claim's parsing exception (e.g. a
malformed PDF) doesn't take down the whole batch, recorded as
`"EXCEPTION: ..."` on that claim's row instead.

**E5. CSV output** (`script.py:194-199`, `_write_rows_csv` at
`script.py:52-74`) — **not a VBA port**, added on top: the VBA writes
`ClaimInfo`/`ClaimServiceLInes` as worksheet tabs (`Main.txt` output
summary); this writes the equivalent two flat structures out as
`ClaimInfo_<timestamp>.csv` / `ClaimServiceLInes_<timestamp>.csv` in
`dest_dir` instead, since there's no workbook here to hold sheets. Header
is the union of every key seen across rows (a skipped claim only has
`CLAIM_NO`/`MACRO_STATUS`/`CLAIM_TYPE`; a fully-extracted one has every
`ClaimInfo`/`ClaimServiceLInes` column) so no column silently drops.

## Summary of what's worth independently verifying against a real claim

In rough priority order, since these are the parts flagged as unverified
rather than confirmed correct:

1. **`pdf_backend.py`'s coordinate scale** (section D) — if nothing
   extracts at all, or everything is misaligned, start here.
2. **`_parse_search_result()`** (A3) — if sign-in succeeds but claims
   still come back "not found," the JSON-shape assumption here is the
   likely culprit.
3. **Repricing info's legacy `KeyPattern` gap** (C4) — expect blank
   `REPRICE_*`/`DISCOUNT_*` fields specifically on legacy-path
   (`use_new_api="N"`) claims.
4. **Method-field index selection** (C4) — same legacy-path caveat, a
   narrower field.
5. **COB adjustment-detail walk and Medicare COB per-line** (C3, C5) —
   both already flagged as fragile in the VBA itself, not just the port.
