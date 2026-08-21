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
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

LEGACY_WEBCLAIMS_URL = "https://umrwebclaims.optum.com/webclaims/index.php"
NEW_WEBCLAIMS_DOMAIN = "https://umrwebclaims-prod.optum.com"


def clean_values(val: str) -> str:
    """Mirrors CLEAN_VALUES VBA — strip stray quotes/braces from a raw scrape."""
    return (val or "").replace('"', "").replace("}", "").strip().upper()


def download_file(url: str, local_path: str, session: "requests.Session | None" = None) -> bool:
    """Mirrors DownloadFile (URLDownloadToFile) VBA, via a streamed HTTP GET."""
    http = session or requests
    try:
        resp = http.get(url, timeout=60, stream=True)
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
        resp = requests.post(LEGACY_WEBCLAIMS_URL, data=params, timeout=60)
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

        try:
            if self.authenticated:
                resp = self._http.post(search_url, json=payload, timeout=60)
            else:
                resp = self._http.post(NEW_WEBCLAIMS_DOMAIN, json=payload, timeout=60)
                if resp.status_code == 200 and "<head>" in resp.text.lower():
                    # OIDC-style sign-in redirect: response is a login form
                    # whose hidden inputs carry the code/state to post back.
                    soup = BeautifulSoup(resp.text, "html.parser")
                    resp = self._http.post(
                        f"{NEW_WEBCLAIMS_DOMAIN}/signin-oidc?action=submit",
                        data={
                            "code": _hidden_value(soup, "code"),
                            "state": _hidden_value(soup, "state"),
                            "session_state": _hidden_value(soup, "session_state"),
                        },
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
            return "PDF Claim not found.", ""

        self.authenticated = True
        row_id, ctype, err_msg = _parse_search_result(body)

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
