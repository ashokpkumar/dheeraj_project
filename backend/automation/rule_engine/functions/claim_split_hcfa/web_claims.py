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

WebClaimsSession's sign-in also needs Windows Integrated Authentication:
umrwebclaims-prod.optum.com's "not authenticated yet" path redirects out to
Microsoft Entra ID (the .AspNetCore.OpenIdConnect.Nonce.*/buid/fpc/esctx/
stsservicecookie cookies it sets are Microsoft's login-server cookies, not
this app's), which on a domain-joined Windows machine normally completes
silently via Kerberos/Seamless SSO — that's what lets the VBA macro (riding
on WinINet through MSXML2.XMLHTTP) get an already-signed-in code/state/
session_state callback page straight away. Plain `requests` doesn't
negotiate that on its own and instead lands on Microsoft's real interactive
sign-in page (no code/state/session_state to find there), so
`requests_negotiate_sspi.HttpNegotiateAuth` is attached to the session
below to do that negotiation the same way WinINet does. Needs `pywin32` +
`requests-negotiate-sspi` (Windows-only — degrades to no SSO auth, with a
warning, if either import fails, e.g. when this module is imported on a
non-Windows dev box).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests
import urllib3
from bs4 import BeautifulSoup

try:
    from requests_negotiate_sspi import HttpNegotiateAuth
except Exception:
    HttpNegotiateAuth = None

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

        try:
            if self.authenticated:
                log("already authenticated (session reused) — posting straight to /Search")
                resp = self._http.post(search_url, json=payload, timeout=60)
                log(f"/Search -> HTTP {resp.status_code}")
            else:
                log(f"not authenticated yet — probing POST {NEW_WEBCLAIMS_DOMAIN}")
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

        body = resp.text
        log(f"final response body preview: {body[:300]!r}")
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
    Mirrors the VBA's own manual slicing of the search response — it isn't
    parsed as real JSON there either; it hand-splits around
    `"Unauthorized":` and reads KEY:VALUE pairs out with string functions.
    This is a regex approximation of that, so it's exposed to the same
    fragility as the original: it assumes flat `"KEY":"VALUE"` pairs and
    will miss anything nested. *** Validate against a real API response. ***
    """
    row_id = ctype = err_msg = ""
    for key, val in re.findall(r'"([A-Za-z]+)"\s*:\s*"?([^",}]*)"?', body):
        key_up = key.upper()
        if key_up == "ROWID":
            row_id = clean_values(val)
        elif key_up == "CLAIMTYPE":
            ctype = clean_values(val)
        elif key_up == "ERRORMSG":
            err_msg = clean_values(val)
    return row_id, ctype, err_msg
