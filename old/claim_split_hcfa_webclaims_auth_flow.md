# Claim Split HCFA — WebClaims sign-in flow (`web_claims.py` vs `oWebClaim.txt`)

How `WebClaimsSession.fetch_claim()` in
`backend/automation/rule_engine/functions/claim_split_hcfa/web_claims.py`
authenticates against `umrwebclaims-prod.optum.com`, step by step, each one
tagged with exactly what VBA line(s) it corresponds to in
`backend/automation/rule_engine/functions/claim_split_hcfa/Macro/oWebClaim.txt`
(function `NEW_WEBLCLAIM`) — or flagged **NEW** where there's no VBA
equivalent to check it against.

Use this to cross-check the port line-by-line; it's a walkthrough, not a
substitute for reading the actual code.

## Background

`umrwebclaims-prod.optum.com`'s "not authenticated yet" path is a plain
`302` (not a `401`) straight to `login.microsoftonline.com`, which returns
a JS-rendered Azure AD sign-in SPA shell — no static `code`/`state`/
`session_state` to scrape until real sign-in completes. Confirmed via
debug logging that this is **not** a classic Windows-Integrated `401`
challenge: there's no `401` for SSPI/Kerberos to react to.

What lets the VBA macro (riding on WinINet through `MSXML2.XMLHTTP`) sail
through with zero prompts is that WinINet shares the same cookie/SSO state
as Edge — by the time the macro runs, Edge already carries a live Azure AD
session that `login.microsoftonline.com` recognizes immediately.
`requests.Session()` starts empty and has no way to see that, so steps 2–3
below exist purely to bridge that gap. Everything from step 4 onward is a
straight port of the VBA.

## Setup (matches VBA 1:1)

**1. Build the search payload** — `web_claims.py:326-335` builds the same
fields as VBA's `wPRM` JSON string (`oWebClaim.txt:27-34`): `SearchType`,
`CCN`, `CustomId`, `DateMinLong`, `DateMaxLong`, `ClaimType`, `Direction`,
`Timeline`. Same values, built as a Python dict passed via `json=payload`
instead of a hand-built JSON string.

## NEW — not in the VBA, added to reach what WinINet gets for free

**2. SSPI attach** (`web_claims.py:313-318`) — attaches
`HttpNegotiateAuth` to the session. **Confirmed currently inert**: the
debug logs showed `umrwebclaims-prod.optum.com` returns a `302`, never a
`401`, so this auth handler never has anything to negotiate against. Kept
only in case that ever changes. No VBA equivalent — VBA would get
Windows-Integrated Auth for free from WinINet transport-level, if/when
it's even used.

**3. Edge SSO bridge** (`web_claims.py:342-348`, calling
`_bridge_edge_sso`) — the real substitute for what VBA gets for free.
Runs once per `WebClaimsSession` instance (not once per claim):

- 3a. Launch headless Edge against a dedicated, automation-only profile
  (`EDGE_SSO_PROFILE_DIR`, under `%LOCALAPPDATA%\ClaimSplitHCFA\
  EdgeSSOProfile` — never your everyday Edge profile), navigate to
  `NEW_WEBCLAIMS_DOMAIN`.
- 3b. If that lands anywhere other than `login.microsoftonline.com`,
  harvest cookies → done, `self.authenticated = True`.
- 3c. If it still lands on the Microsoft sign-in page, launch a
  **visible** Edge window and wait up to 5 minutes for a manual sign-in.
- 3d. Import whatever cookies resulted into `self._http.cookies`.

No VBA counterpart to check this against — VBA never has to do this
because WinINet already carries the signed-in Edge session automatically.

(An earlier version of this bridge tried copying the *live* Edge profile
directly instead of using a dedicated one. That hit a hard OS-level wall:
Windows file sharing is mutual, so if Edge has a file open exclusively, no
amount of permissive sharing requested on the read side can get through
while Edge is running — `PermissionError: [WinError 32]`. The dedicated
profile sidesteps that entirely since nothing else ever opens it.)

## From here on: a faithful line-by-line port of `NEW_WEBLCLAIM`

**4. Branch on `self.authenticated`** (`web_claims.py:350-354`) = VBA's
`If blnAUTH = True Then GoTo URL_SEARCH` (`oWebClaim.txt:42`). If true
(either the Edge bridge just set it, or a prior claim in this same session
already authenticated), POST straight to `/Search` — same as VBA's
`URL_SEARCH:` label (`oWebClaim.txt:69-71`).

**5. If not authenticated — the probe** (`web_claims.py:359`) = VBA's
`.Open "POST", wURL_DOMAIN, False ... .send wPRM` (`oWebClaim.txt:43`).
POST the same payload to the bare domain.

**6. Branch on status** (`web_claims.py:379-439`) = VBA's
`Select Case .Status` (`oWebClaim.txt:45-77`):

- **`200` + response contains `<head>`** (`web_claims.py:379`) = VBA
  `Case 200` / `If InStr(1, rE, "<head>", 0) > 0` (`oWebClaim.txt:46-47`).
  - Extract `code`/`state`/`session_state` hidden inputs
    (`web_claims.py:382-385`) = VBA's
    `hDOC.getElementsByTagName("input").Item(...)` (`oWebClaim.txt:49-52`).
  - Build the **raw, un-urlencoded** body and POST to
    `/signin-oidc?action=submit` (`web_claims.py:406-413`) = VBA's
    `wPARAM = "&code=" & ... .send wPARAM` (`oWebClaim.txt:53-56`) —
    deliberately byte-for-byte: `requests`' default `data={...}` would
    urlencode these values, which the VBA never does, and mismatched
    encoding was a real suspect earlier for a Python-only 500.
  - `200` → `authenticated = True`, replay `/Search`
    (`web_claims.py:422-425`) = VBA
    `Case 200: blnAUTH = True ... .send wPRM` (`oWebClaim.txt:58-61`).
  - else → fail, return error (`web_claims.py:418-421`) = VBA
    `Case Else: blnAUTH = False: MsgBox ... End` (`oWebClaim.txt:62-65`) —
    Python returns an error string instead of a blocking dialog + process
    kill, since a server-side job can't show a `MsgBox`.
- **`405`** (`web_claims.py:426-431`) = VBA `Case 405` →
  `URL_SEARCH:` (`oWebClaim.txt:68-72`): POST straight to `/Search`,
  `authenticated = True`.
- **anything else** (`web_claims.py:432-436`) = VBA `Case Else`
  (`oWebClaim.txt:73-76`): fail, return error.

**7. Check for an empty result** (`web_claims.py:447-451`) = VBA's
`If rE <> "{""Authorized"":[],""Unauthorized"":[]}" Then ... Else:
blnAUTH = False: GoTo JUSTEXIT` (`oWebClaim.txt:78-90`) — same string,
condition just inverted (Python checks the equality directly and returns
early instead of `GoTo`).

**8. Parse the result** (`web_claims.py:454`, `_parse_search_result` at
line 473) = VBA's manual string-splitting for `ROWID`/`CLAIMTYPE`/
`ERRORMSG` (`oWebClaim.txt:80-110`). **Flagged in the code as unverified**
(`web_claims.py:474-480`) — it's a regex approximation of VBA's
hand-rolled slicing, not yet tested against a real API response body.
Worth checking closely once execution reaches this point: a field-name
mismatch here would fail silently as "PDF Claim not found."

**9. Download the PDF** (`web_claims.py:462-464`) = VBA's
`DownloadFile wURL_GENPDF & "rowid=" & ROWID & "&ccn=" & CCN, ...`
(`oWebClaim.txt:112-117`).

**Not ported**: VBA's `.abort` (`oWebClaim.txt:111`) has no Python
equivalent — that's VBA cancelling a request object that's already
finished; `requests` calls are synchronous and there's nothing left to
abort by the time execution reaches that point.

## Open question

Everything from step 4 onward is a straight port either way. Step 3 (the
Edge SSO bridge) is new architecture, not a translation of existing VBA
logic — worth an explicit call on whether a browser-based SSO bridge is
an acceptable approach for this system long-term, versus alternatives
(e.g. a Volume Shadow Copy snapshot of the live Edge profile, which needs
admin rights) that were considered and set aside during debugging.
