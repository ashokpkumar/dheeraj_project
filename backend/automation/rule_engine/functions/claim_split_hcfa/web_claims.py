"""
Claim Split HCFA — PART 1: fetching a claim's PDF from the web.

Ports oWebClaim.txt. This is the "scraping" half of the macro — everything
here talks to an HTTP portal, not the mainframe. The mainframe-automation
half lives in cps_entry.py.

Two retrieval paths existed in the VBA, selected by the `chkWbClaim`
checkbox (here: the `use_new_api` flag passed in from script.py):

  * get_pdf_claim_legacy()  — mirrors Get_PDF_Claim2: scrapes the legacy PHP
    claim viewer with a raw HTTP POST + HTML table parse for a PDF link.
  * WebClaimsSession.fetch_claim() — mirrors NEW_WEBLCLAIM: the newer JSON
    WebClaims API, with a lightweight OIDC-style sign-in handshake.

NOT ported: `Get_PDF_Claim` (the oldest fallback in oWebClaim.txt, driving
Internet Explorer via COM/`InternetExplorerMedium`). It was already
superseded by Get_PDF_Claim2 in the VBA itself, and IE automation isn't a
sane target for a server-side port — flag if it turns out some claims still
need it.

Needs `requests` and `beautifulsoup4` (not yet in requirements.txt — see
the note left at the end of this file's module docstring in script.py).

TLS verification is disabled for every request in this module (see
VERIFY_TLS below) — the corporate network this runs on terminates TLS to
*.optum.com through an inspecting proxy whose root cert isn't in Python's
bundled CA list (though Windows itself trusts it), which otherwise fails
every request with CERTIFICATE_VERIFY_FAILED / self-signed certificate in
certificate chain. This was a deliberate choice over the safer fix (trusting
the Windows cert store, e.g. via pip-system-certs) — flip VERIFY_TLS back to
True if that ever changes.

WebClaimsSession's sign-in needs an already-authenticated Azure AD/Entra ID
session: umrwebclaims-prod.optum.com's "not authenticated yet" path is a
plain 302 (not a 401) straight to login.microsoftonline.com, which returns
a JS-rendered sign-in SPA shell (no static code/state/session_state to
scrape — those only appear after real sign-in completes). That's confirmed
NOT the same as a classic Windows-Integrated 401 challenge:
requests_negotiate_sspi.HttpNegotiateAuth (still attached below, harmless)
never even gets a chance to negotiate, because there's no 401 to react to.

What actually lets the VBA macro (riding on WinINet through MSXML2.XMLHTTP)
sail through with zero prompts is that WinINet shares the same cookie/SSO
state as Edge — by the time the macro runs, Edge already carries a live
Azure AD session (Desktop SSO, or just an existing signed-in M365 session)
that login.microsoftonline.com recognizes immediately. `requests.Session()`
starts empty and has no way to see that.

So `_bridge_edge_sso()` below launches a real Edge (via Playwright,
`channel="msedge"` — the system-installed Edge, not a separate download)
against a DEDICATED profile directory that only this automation ever
touches (NOT your everyday Edge profile — an earlier version tried
reusing that directly and hit a hard OS-level wall: Windows file sharing
is mutual, so if Edge has a file open exclusively, no amount of
permissive sharing requested on our end can read it while Edge is
running; the only real fixes are a Volume Shadow Copy snapshot, which
needs admin rights, or just not touching the live file at all). The first
time this runs (no saved session in that dedicated profile yet, or an
expired one), it opens a real, visible browser window and waits for you
to sign in by hand once — MFA and all. Playwright persists that session
to disk in the dedicated profile, so every run after that reuses it
silently and headlessly, with zero prompts, until it eventually expires.

Needs the `playwright` package (`pip install playwright`; no `playwright
install` browser download needed since channel="msedge" drives your
installed Edge directly) and Edge itself installed. Falls back to the
manual OIDC-probe/signin-oidc dance (and SSPI) below if the bridge can't
run at all (e.g. playwright not installed) — that fallback is expected to
keep landing on the interactive sign-in page per the analysis above, but
it's left in place as a diagnostic trail and in case that ever changes.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field

import requests
import urllib3
from bs4 import BeautifulSoup

try:
    from requests_negotiate_sspi import HttpNegotiateAuth
except Exception:
    HttpNegotiateAuth = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

# See the module docstring above for why this is off.
VERIFY_TLS = False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LEGACY_WEBCLAIMS_URL = "https://umrwebclaims.optum.com/webclaims/index.php"
NEW_WEBCLAIMS_DOMAIN = "https://umrwebclaims-prod.optum.com"


def clean_values(val: str) -> str:
    """Mirrors CLEAN_VALUES VBA — strip stray quotes/braces from a raw scrape."""
    return (val or "").replace('"', "").replace("}", "").strip().upper()


def download_file(url: str, local_path: str, session: "requests.Session | None" = None) -> bool:
    """Mirrors DownloadFile (URLDownloadToFile) VBA, via a streamed HTTP GET."""
    http = session or requests
    try:
        resp = http.get(url, timeout=60, stream=True, verify=VERIFY_TLS)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
        return True
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------------
# Legacy scrape — mirrors Get_PDF_Claim2
# ---------------------------------------------------------------------------

def get_pdf_claim_legacy(claim_control_number: str, dest_dir: str, most_recent: bool = True) -> tuple[str, str]:
    """
    Returns (claim_type_or_error_message, local_pdf_path); local_pdf_path is
    "" on failure. Mirrors Get_PDF_Claim2: POSTs a claim search, scrapes the
    results table for the "view" link + search-sequence token per matching
    row, then downloads the PDF for the (usually first/only) match.
    """
    dest_path = os.path.join(dest_dir, f"{claim_control_number}.pdf")
    if os.path.exists(dest_path):
        os.remove(dest_path)

    params = {
        "action": "submit",
        "bolRestrictedSearch": "",
        "search_field": claim_control_number,
        "search_type": "CCN",
        "search_min": "",
        "search_max": "",
        "search_clm_type": "all",
        "Route[]": "100,500,511,525,570,575,5052",
        "multiclm_opt1": "top" if most_recent else "bottom",
        "db_state": "prod",
    }

    try:
        resp = requests.post(LEGACY_WEBCLAIMS_URL, data=params, timeout=60, verify=VERIFY_TLS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return f"WebClaims request failed: {exc}", ""

    soup = BeautifulSoup(resp.text, "html.parser")

    for b in soup.find_all("b"):
        if "Some CCN search criteria did not yield a result:" in b.get_text():
            return "PDF Claim not found.", ""

    tables = soup.find_all("table")
    if len(tables) < 3:
        return "Unexpected page layout from webclaims (no results table).", ""

    inputs = soup.find_all("input")
    rows = tables[2].find_all("tr")
    claim_type = ""
    got_pdf = False
    cnt_placer = 3

    for row_idx in range(1, len(rows), 2):
        if cnt_placer >= len(inputs):
            break
        raw_name = inputs[cnt_placer].get("name", "")
        btn_click_to_view = (
            raw_name.replace("/", "%2f").replace("+", "%2b") + "%3d&"
        ).replace("submit_", "")
        orig_search_seq = "originalSearchSequence=" + inputs[cnt_placer - 1].get("value", "").replace("=", "%3d")
        pdf_url = f"{LEGACY_WEBCLAIMS_URL}?action=view&searchResult={btn_click_to_view}{orig_search_seq}"

        if download_file(pdf_url, dest_path):
            got_pdf = True
            cells = rows[row_idx].find_all("td")
            claim_type = cells[7].get_text(strip=True) if len(cells) > 7 else ""
        else:
            claim_type = "PDF file download not successful."
        cnt_placer += 6

    if not got_pdf:
        return claim_type or "PDF file download not successful.", ""
    return claim_type, dest_path


# ---------------------------------------------------------------------------
# Edge SSO bridge — not in the VBA, added to reach what WinINet gets for free
# ---------------------------------------------------------------------------

# A profile directory ONLY this automation ever opens — never your everyday
# Edge profile. That's the point: nothing else contends for it, so there's
# no live-file-locking problem to work around (see the module docstring for
# why reusing your real Edge profile turned out to be a dead end). Persists
# across runs under %LOCALAPPDATA% so a signed-in session survives restarts
# of the script, same as your regular Edge profile would.
EDGE_SSO_PROFILE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
    "ClaimSplitHCFA", "EdgeSSOProfile",
)

SIGN_IN_WAIT_MS = 5 * 60 * 1000  # how long a first-time interactive sign-in gets


def _launch_edge_sso_profile(headless: bool, log) -> "list[dict] | None":
    """
    Launches Playwright against EDGE_SSO_PROFILE_DIR and navigates to
    NEW_WEBCLAIMS_DOMAIN. Returns the resulting cookies if that lands
    somewhere other than Microsoft's sign-in page, else None. When
    headless=False and sign-in is still needed, waits (up to
    SIGN_IN_WAIT_MS) for you to complete it by hand in the visible window
    before giving up.
    """
    os.makedirs(EDGE_SSO_PROFILE_DIR, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            EDGE_SSO_PROFILE_DIR, channel="msedge", headless=headless,
        )
        try:
            page = context.new_page()
            page.goto(NEW_WEBCLAIMS_DOMAIN, wait_until="networkidle", timeout=30000)
            log(f"Edge SSO bridge ({'headless' if headless else 'visible'}) landed on: {page.url}")
            if "login.microsoftonline.com" in page.url:
                if headless:
                    return None
                log(f"Edge SSO bridge: a browser window has opened — please sign in "
                    f"(waiting up to {SIGN_IN_WAIT_MS // 60000} minute(s))...")
                try:
                    page.wait_for_url(lambda url: "login.microsoftonline.com" not in url, timeout=SIGN_IN_WAIT_MS)
                except Exception:
                    log("Edge SSO bridge: timed out waiting for you to sign in")
                    return None
                log(f"Edge SSO bridge: signed in, landed on: {page.url}")
            return context.cookies()
        finally:
            context.close()


def _bridge_edge_sso(log) -> "requests.cookies.RequestsCookieJar | None":
    """
    Gets an authenticated Azure AD session for NEW_WEBCLAIMS_DOMAIN via a
    dedicated, automation-only Edge profile (see EDGE_SSO_PROFILE_DIR):
    tries headlessly first (silent — works once you've signed in at least
    once before and that session hasn't expired), and if that lands on
    Microsoft's sign-in page, opens a real visible window and waits for you
    to sign in by hand once. Returns the resulting cookies as a
    RequestsCookieJar for `requests` to reuse, or None (after logging why)
    if playwright isn't installed or sign-in doesn't complete.
    """
    if sync_playwright is None:
        log("Edge SSO bridge unavailable: `playwright` is not installed "
            "(pip install playwright — channel=msedge drives your installed "
            "Edge directly, no `playwright install` browser download needed)")
        return None

    cookies = None
    try:
        cookies = _launch_edge_sso_profile(headless=True, log=log)
        if cookies is None:
            log("Edge SSO bridge: no valid saved session yet in the dedicated profile — "
                "opening a visible window for a one-time interactive sign-in")
            cookies = _launch_edge_sso_profile(headless=False, log=log)
    except Exception as exc:
        log(f"Edge SSO bridge failed: {type(exc).__name__}: {exc}")

    if not cookies:
        return None

    jar = requests.cookies.RequestsCookieJar()
    for c in cookies:
        jar.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))
    log(f"Edge SSO bridge succeeded — imported {len(cookies)} cookie(s)")
    return jar


# ---------------------------------------------------------------------------
# New JSON API — mirrors NEW_WEBLCLAIM
# ---------------------------------------------------------------------------

@dataclass
class WebClaimsSession:
    """
    Holds sign-in state across calls, mirroring the VBA module-level
    `Public blnAUTH As Boolean`. Create ONE instance per worker/thread (each
    parallel emulator-session worker in script.py should own its own), not
    a shared global — cookies/auth state shouldn't be shared across
    concurrently-running fetches.
    """

    authenticated: bool = False
    _http: "requests.Session" = field(default_factory=requests.Session)
    _tried_edge_bridge: bool = field(default=False, repr=False)

    def __post_init__(self):
        # Applies to every request made through this session, including the
        # download_file(session=self._http) call in fetch_claim() below.
        self._http.verify = VERIFY_TLS
        # Windows Integrated Auth (Kerberos/NTLM via SSPI) — see the module
        # docstring for why this is needed to reach the same
        # already-signed-in code/state/session_state page WinINet gets the
        # VBA macro. Without it, the domain-root probe in fetch_claim()
        # below lands on Microsoft's real interactive sign-in page instead.
        if HttpNegotiateAuth is not None:
            self._http.auth = HttpNegotiateAuth()
        else:
            print("[WebClaimsSession] WARNING: requests_negotiate_sspi not available — "
                  "sign-in will land on Microsoft's interactive login page and fail. "
                  "Install pywin32 + requests-negotiate-sspi (Windows only).")

    def fetch_claim(self, claim_control_number: str, dest_dir: str, most_recent: bool = True) -> tuple[str, str]:
        """Returns (claim_type_or_error_message, local_pdf_path)."""
        dest_path = os.path.join(dest_dir, f"{claim_control_number}.pdf")
        if os.path.exists(dest_path):
            os.remove(dest_path)

        payload = {
            "SearchType": "1",       # 1=CCN, 2=Member ID, 3=Alternate claim#
            "CCN": claim_control_number,
            "CustomId": "",
            "DateMinLong": 0,
            "DateMaxLong": 0,
            "ClaimType": 1,          # 1=All, 2=HCFA, 3=UB, 4=ADA
            "Direction": 0,          # 0=All, 1=Inbound, 2=Outbound
            "Timeline": 1 if most_recent else 2,
        }
        search_url = f"{NEW_WEBCLAIMS_DOMAIN}/Search"
        gen_pdf_url = f"{NEW_WEBCLAIMS_DOMAIN}/PDFGeneration"

        log = lambda msg: print(f"[WebClaimsSession {claim_control_number}] {msg}")
        log(f"SSPI Negotiate auth attached: {self._http.auth is not None}")

        log("=== PHASE 1: AUTH === (must complete, and self.authenticated must be True, "
            "before PHASE 2 sends anything claim-specific below)")
        if not self.authenticated and not self._tried_edge_bridge:
            self._tried_edge_bridge = True
            jar = _bridge_edge_sso(log)
            if jar is not None:
                self._http.cookies.update(jar)
                self.authenticated = True
                log("Edge SSO bridge cookies imported into this session")
        log(f"=== PHASE 1 DONE === self.authenticated={self.authenticated}")

        log("=== PHASE 2: SEARCH ===")
        try:
            if self.authenticated:
                log("already authenticated (session reused) — posting straight to /Search")
                resp = self._http.post(search_url, json=payload, timeout=60)
                log(f"/Search -> HTTP {resp.status_code}")
            else:
                log(f"not authenticated yet, Edge SSO bridge unavailable — falling back to "
                    f"the manual OIDC probe (expected to hit the interactive sign-in page — "
                    f"see module docstring); probing POST {NEW_WEBCLAIMS_DOMAIN}")
                resp = self._http.post(NEW_WEBCLAIMS_DOMAIN, json=payload, timeout=60)
                log(f"probe -> HTTP {resp.status_code}, {len(resp.text)} byte(s), "
                    f"looks like HTML={'<head>' in resp.text.lower()}")
                log(f"final landed URL: {resp.url}")
                if resp.history:
                    log(f"redirect chain ({len(resp.history)} hop(s)):")
                    for hop in resp.history:
                        log(f"  {hop.status_code} {hop.url} -> "
                            f"Location: {hop.headers.get('Location', '')!r}, "
                            f"Authorization header sent: {'Authorization' in hop.request.headers}")
                    log(f"  (final) {resp.status_code} {resp.url} -> "
                        f"Authorization header sent: {'Authorization' in resp.request.headers}")
                else:
                    log(f"no redirects — Authorization header sent on this request: "
                        f"{'Authorization' in resp.request.headers}")
                title_match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
                log(f"response <title>: {title_match.group(1).strip() if title_match else '(none found)'}")
                log("looks like a REAL Microsoft interactive sign-in form "
                    f"(has id=\"i0116\" username field): {'i0116' in resp.text}")
                log(f"session cookies after probe: {list(self._http.cookies.keys())}")
                if resp.status_code == 200 and "<head>" in resp.text.lower():
                    # OIDC-style sign-in redirect: response is a login form
                    # whose hidden inputs carry the code/state to post back.
                    soup = BeautifulSoup(resp.text, "html.parser")
                    code_val = _hidden_value(soup, "code")
                    state_val = _hidden_value(soup, "state")
                    session_val = _hidden_value(soup, "session_state")
                    log(f"got login page — hidden fields found: code={bool(code_val)}, "
                        f"state={bool(state_val)}, session_state={bool(session_val)}"
                        + ("" if (code_val and state_val and session_val)
                           else " <-- one or more MISSING, sign-in will likely fail; "
                                "the portal's login page markup may not match what "
                                "_hidden_value() expects (check input names)"))
                    # NOTE: sent as a raw, NOT urlencoded body — matching the
                    # VBA's `"&code=" & reCode & "&state=" & re_STATE & ...`
                    # exactly, byte for byte. requests.post(..., data={...})
                    # would run code_val/state_val/session_val through
                    # urlencode() first, which percent-encodes characters
                    # (+, /, =) that OIDC code/session_state values commonly
                    # contain. If the endpoint does anything naive with the
                    # body, that "correctly encoded" value is actually a
                    # DIFFERENT value than what VBA sends — plausible cause
                    # of a 500 in Python that the macro doesn't hit. If this
                    # turns out not to be it, switch back to
                    # data={"code": code_val, "state": state_val,
                    # "session_state": session_val} and dig into the
                    # response body logged below instead.
                    raw_body = f"&code={code_val}&state={state_val}&session_state={session_val}"
                    log(f"signin-oidc POST body (raw, unencoded): {raw_body!r}")
                    resp = self._http.post(
                        f"{NEW_WEBCLAIMS_DOMAIN}/signin-oidc?action=submit",
                        data=raw_body.encode("utf-8"),
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=60,
                    )
                    log(f"signin-oidc POST -> HTTP {resp.status_code}")
                    log(f"signin-oidc response headers: {dict(resp.headers)}")
                    log(f"signin-oidc response body ({len(resp.text)} chars): {resp.text[:2000]!r}")
                    log(f"session cookies after signin-oidc: {list(self._http.cookies.keys())}")
                    if resp.status_code != 200:
                        self.authenticated = False
                        log("AUTH FAILED at signin-oidc step")
                        return f"WEBCLAIM: UNEXPECTED ERROR OCCURRED (sign-in, HTTP {resp.status_code})", ""
                    self.authenticated = True
                    log("AUTH OK — replaying /Search")
                    resp = self._http.post(search_url, json=payload, timeout=60)
                    log(f"/Search (post-auth) -> HTTP {resp.status_code}")
                elif resp.status_code == 405:
                    log("probe returned 405 (Method Not Allowed) — treating as already-authenticated "
                        "path and retrying directly against /Search")
                    resp = self._http.post(search_url, json=payload, timeout=60)
                    self.authenticated = True
                    log(f"/Search (405 path) -> HTTP {resp.status_code}")
                elif resp.status_code != 200:
                    self.authenticated = False
                    log(f"AUTH FAILED: probe returned unexpected HTTP {resp.status_code} "
                        f"(not 200, not 405). Body preview: {resp.text[:300]!r}")
                    return f"WEBCLAIM: UNEXPECTED ERROR OCCURRED (HTTP {resp.status_code})", ""
                else:
                    log("probe returned 200 with no <head> — treating response as the real "
                        "search result (no sign-in needed)")
        except requests.RequestException as exc:
            self.authenticated = False
            log(f"REQUEST EXCEPTION during auth/search: {exc}")
            return f"WebClaims API request failed: {exc}", ""

        log("=== PHASE 3: PARSE + DOWNLOAD ===")
        body = resp.text
        log(f"/Search response: HTTP {resp.status_code}, {len(body)} byte(s), "
            f"Content-Type: {resp.headers.get('Content-Type', '')!r}")
        log(f"/Search FULL response body: {body!r}")
        if body == '{"Authorized":[],"Unauthorized":[]}':
            self.authenticated = False
            log("AUTH FAILED: server returned empty Authorized/Unauthorized — session was not "
                "actually accepted despite earlier 200s")
            return "PDF Claim not found.", ""

        self.authenticated = True
        row_id, ctype, err_msg = _parse_search_result(body)
        log(f"parsed search result: row_id={row_id!r}, claim_type={ctype!r}, err_msg={err_msg!r}")

        if err_msg and err_msg != "NULL":
            return err_msg, ""
        if not row_id:
            log("PDF Claim not found — but the body above was NOT the canned empty-result "
                "string, and this reached the search successfully (authenticated). If that "
                "body actually contains this claim's data, _parse_search_result()'s regex "
                "isn't matching this response's real JSON shape — compare the body above "
                "against what _parse_search_result() expects (ROWID/CLAIMTYPE/ERRORMSG keys).")
            return "PDF Claim not found.", ""

        pdf_url = f"{gen_pdf_url}?rowid={row_id}&ccn={claim_control_number}"
        if not download_file(pdf_url, dest_path, session=self._http):
            return "PDF file download not successful.", ""
        return ctype, dest_path


def _hidden_value(soup: "BeautifulSoup", name: str) -> str:
    tag = soup.find("input", {"name": name})
    return tag.get("value", "") if tag else ""


def _parse_search_result(body: str) -> tuple[str, str, str]:
    """
    Parses the /Search response's real shape, confirmed against a live
    response (2026-08-26):

        {"Authorized":[{"RowID":9593990523,"SearchTerm":"...",
          "ClaimType":"HCFA", ..., "CentralSecurity":{"isAuthenticated":
          "YES","ccn":"...","errorMsg":null}}],"Unauthorized":[]}

    This USED to be a regex approximation of the VBA's own manual
    string-slicing (it doesn't parse real JSON there either — it
    hand-splits around `"Unauthorized":` and reads KEY:VALUE pairs with
    string functions). That regex had a real, confirmed bug: matching
    `"KEY":` pairs with an optional trailing quote on the value
    (`"?([^",}]*)"?`) means that whenever a value is unquoted — like
    `"Authorized":[{` above, where `[{` isn't a quoted scalar — the
    trailing `"?` greedily swallows the *next* key's opening quote,
    corrupting `re.findall`'s position enough that the immediately
    following key (here, `RowID` — the one field this function most
    needs) gets silently skipped. That's exactly what was happening:
    `ClaimType` parsed fine (nothing before it ate its opening quote),
    `RowID` came back empty every time despite being right there in the
    body. Real JSON, now that its shape is confirmed, has no such
    ambiguity — parse it properly instead of patching the regex further.

    Falls back to "Unauthorized"'s first entry if "Authorized" is empty,
    so a claim that's present but not authorized for this session still
    surfaces its errorMsg instead of just "PDF Claim not found."
    """
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return "", "", ""

    entries = data.get("Authorized") or data.get("Unauthorized") or []
    if not entries:
        return "", "", ""

    entry = entries[0]
    row_id = clean_values(str(entry.get("RowID", "")))
    ctype = clean_values(str(entry.get("ClaimType", "")))
    central_security = entry.get("CentralSecurity") or {}
    err_msg = clean_values(str(central_security.get("errorMsg") or entry.get("ErrorMsg") or "NULL"))
    return row_id, ctype, err_msg
