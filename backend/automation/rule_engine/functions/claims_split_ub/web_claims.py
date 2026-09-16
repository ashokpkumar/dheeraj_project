"""
Claims Split UB — PART 1: fetching a claim's PDF from the web.

Ports oWebClaim.txt. This is the "scraping" half of the macro — everything
here talks to an HTTP portal, not the mainframe. The mainframe-automation
half lives in cps_entry.py.

Two retrieval paths existed in the VBA, selected by the `chkWbClaim`
checkbox (here: the `use_new_api` flag passed in from script.py):

  * get_pdf_claim_legacy()  — mirrors Get_PDF_Claim_New: a plain HTTP
    POST/GET scrape of the legacy PHP claim viewer, no browser involved.
    (Despite the VBA function's name containing "New", this is the OLDER
    of the two API-style paths — "New" there means "no longer uses
    Internet Explorer", not "the newest option overall". It's the same
    endpoint/param shape as claim_split_hcfa's Get_PDF_Claim2/
    get_pdf_claim_legacy, confirmed byte-for-byte identical URL and POST
    body construction between the two macros' oWebClaim.txt.)
  * WebClaimsSession.fetch_claim() — mirrors NEW_WEBLCLAIM: the newer JSON
    WebClaims API, with a lightweight OIDC-style sign-in handshake.
    Byte-for-byte identical VBA to claim_split_hcfa's NEW_WEBLCLAIM (same
    domain, same payload shape, same auth dance) — ported here unchanged
    from that module.

NOT ported: `Get_PDF_Claim_Old` (oWebClaim.txt's oldest fallback, driving
Internet Explorer via COM/`InternetExplorerMedium`) — same call as
claim_split_hcfa's decision not to port its own IE-driven `Get_PDF_Claim`:
it was already superseded by the non-IE path in the VBA itself, and IE
automation isn't a sane target for a server-side port. Flag if it turns out
some claims still need it.

Needs `requests` and `beautifulsoup4` (already added to requirements.txt by
the claim_split_hcfa port — see that package's script.py docstring).

TLS verification is disabled for every request in this module (see
VERIFY_TLS below) — see claim_split_hcfa/web_claims.py's module docstring
for the full explanation (corporate TLS-inspecting proxy whose root cert
isn't in Python's bundled CA list). Same tradeoff, same fix if that changes.

WebClaimsSession's sign-in needs an already-authenticated Azure AD/Entra ID
session — see claim_split_hcfa/web_claims.py's module docstring for the
full Edge-SSO-bridge explanation (`_bridge_edge_sso()` below is an unchanged
copy of that mechanism, not re-derived for this macro).
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
# Legacy scrape — mirrors Get_PDF_Claim_New
# ---------------------------------------------------------------------------

def get_pdf_claim_legacy(claim_control_number: str, dest_dir: str, most_recent: bool = True) -> tuple[str, str]:
    """
    Returns (claim_type_or_error_message, local_pdf_path); local_pdf_path is
    "" on failure. Mirrors Get_PDF_Claim_New: POSTs a claim search (identical
    URL/params to claim_split_hcfa's get_pdf_claim_legacy — confirmed against
    both macros' oWebClaim.txt), scrapes the results table for the "view"
    link + search-sequence token per matching row, then downloads the PDF for
    the (usually first/only) match.
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
        text = b.get_text()
        if "Some CCN search criteria did not yield a result:" in text:
            return "Not Found.", ""
        if "PLEASE PROVIDE SEARCH CRITERIA" in text:
            return "CCN Missing.", ""

    tables = soup.find_all("table")
    if len(tables) < 3:
        return "Unexpected page layout from webclaims (no results table).", ""

    inputs = soup.find_all("input")
    rows = tables[2].find_all("tr")
    claim_type = ""
    got_pdf = False
    cnt_placer = 3
    row_idx = 1

    # Mirrors `Do While Len(Trim(objHtmlTable(2).Rows(tblRw).Cells(5).innerText)) > 0`
    while row_idx < len(rows):
        cells = rows[row_idx].find_all("td")
        if len(cells) <= 5 or not cells[5].get_text(strip=True):
            break
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
            claim_type = cells[7].get_text(strip=True) if len(cells) > 7 else ""
        else:
            claim_type = "Not Found."
        row_idx += 1
        cnt_placer += 6

    if not got_pdf and not claim_type:
        return "Not Found.", ""
    if not got_pdf:
        return claim_type, ""
    return claim_type, dest_path


# ---------------------------------------------------------------------------
# Edge SSO bridge — not in the VBA, added to reach what WinINet gets for free
# ---------------------------------------------------------------------------

# A profile directory ONLY this automation ever opens — kept separate from
# claim_split_hcfa's own EDGE_SSO_PROFILE_DIR (different subfolder) so the
# two macros' sign-in sessions/cookie jars never collide if both run on the
# same machine. See claim_split_hcfa/web_claims.py's module docstring for
# the full rationale (why a dedicated profile at all, why not your real
# Edge profile).
EDGE_SSO_PROFILE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
    "ClaimsSplitUB", "EdgeSSOProfile",
)

SIGN_IN_WAIT_MS = 5 * 60 * 1000  # how long a first-time interactive sign-in gets


def _launch_edge_sso_profile(headless: bool, log, keep_open_ms: int = 0) -> "list[dict] | None":
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
            elif keep_open_ms:
                log(f"Edge SSO bridge: already signed in — keeping the window open "
                    f"{keep_open_ms / 1000:.0f}s so it's visible")
                page.wait_for_timeout(keep_open_ms)
            return context.cookies()
        finally:
            context.close()


def _bridge_edge_sso(log, show_browser: bool = False) -> "requests.cookies.RequestsCookieJar | None":
    """Gets an authenticated Azure AD session for NEW_WEBCLAIMS_DOMAIN via a
    dedicated, automation-only Edge profile (see EDGE_SSO_PROFILE_DIR)."""
    if sync_playwright is None:
        log("Edge SSO bridge unavailable: `playwright` is not installed "
            "(pip install playwright — channel=msedge drives your installed "
            "Edge directly, no `playwright install` browser download needed)")
        return None

    cookies = None
    try:
        if show_browser:
            log("Edge SSO bridge: show_browser=True — opening a visible window")
            cookies = _launch_edge_sso_profile(headless=False, log=log, keep_open_ms=3000)
        else:
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
# New JSON API — mirrors NEW_WEBLCLAIM (byte-identical VBA to claim_split_hcfa)
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
    show_browser: bool = False
    _http: "requests.Session" = field(default_factory=requests.Session)
    _tried_edge_bridge: bool = field(default=False, repr=False)

    def __post_init__(self):
        self._http.verify = VERIFY_TLS
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

        if not self.authenticated and not self._tried_edge_bridge:
            self._tried_edge_bridge = True
            jar = _bridge_edge_sso(log, show_browser=self.show_browser)
            if jar is not None:
                self._http.cookies.update(jar)
                self.authenticated = True
                log("Edge SSO bridge cookies imported into this session")

        try:
            if self.authenticated:
                resp = self._http.post(search_url, json=payload, timeout=60)
            else:
                resp = self._http.post(NEW_WEBCLAIMS_DOMAIN, json=payload, timeout=60)
                if resp.status_code == 200 and "<head>" in resp.text.lower():
                    soup = BeautifulSoup(resp.text, "html.parser")
                    code_val = _hidden_value(soup, "code")
                    state_val = _hidden_value(soup, "state")
                    session_val = _hidden_value(soup, "session_state")
                    raw_body = f"&code={code_val}&state={state_val}&session_state={session_val}"
                    resp = self._http.post(
                        f"{NEW_WEBCLAIMS_DOMAIN}/signin-oidc?action=submit",
                        data=raw_body.encode("utf-8"),
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=60,
                    )
                    if resp.status_code != 200:
                        self.authenticated = False
                        return f"WEBCLAIM: UNEXPECTED ERROR OCCURRED (sign-in, HTTP {resp.status_code})", ""
                    self.authenticated = True
                    resp = self._http.post(search_url, json=payload, timeout=60)
                elif resp.status_code == 405:
                    resp = self._http.post(search_url, json=payload, timeout=60)
                    self.authenticated = True
                elif resp.status_code != 200:
                    self.authenticated = False
                    return f"WEBCLAIM: UNEXPECTED ERROR OCCURRED (HTTP {resp.status_code})", ""
        except requests.RequestException as exc:
            self.authenticated = False
            return f"WebClaims API request failed: {exc}", ""

        body = resp.text
        if body == '{"Authorized":[],"Unauthorized":[]}':
            self.authenticated = False
            return "Not Found.", ""

        self.authenticated = True
        row_id, ctype, err_msg = _parse_search_result(body)

        if err_msg and err_msg != "NULL":
            return err_msg, ""
        if not row_id:
            return "Not Found.", ""

        pdf_url = f"{gen_pdf_url}?rowid={row_id}&ccn={claim_control_number}"
        if not download_file(pdf_url, dest_path, session=self._http):
            return "PDF file download not successful.", ""
        return ctype, dest_path


def _hidden_value(soup: "BeautifulSoup", name: str) -> str:
    tag = soup.find("input", {"name": name})
    return tag.get("value", "") if tag else ""


def _parse_search_result(body: str) -> tuple[str, str, str]:
    """See claim_split_hcfa/web_claims.py's `_parse_search_result` for the
    full explanation of the real /Search response shape — identical parsing
    logic, this macro's WebClaims API is the same endpoint."""
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
