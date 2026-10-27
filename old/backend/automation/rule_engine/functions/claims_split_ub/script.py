"""
Claims Split UB — main registered functions.

Ports Main.txt's two real actions ("02.GET EDI DETAILS" and "03.SPLIT
CLAIM" — "01.CLEAN ALL SHEETS" doesn't apply here, there's no worksheet to
clear) as two separate `@register_function` entries, same convention as
claim_split_hcfa/script.py:

  claims_split_ub_get_edi_details()  — PART 1 (web_claims.py + pdf_extract.py):
      fetches each claim's PDF from the web and parses it into two
      DataFrames, mirroring the VBA's two-sheet split (ClaimInfo /
      ClaimServiceLInes). Pure I/O — no emulator session needed. HCFA
      claims are reported and skipped — this macro only supports UB, the
      mirror image of claim_split_hcfa's own "UB CLAIM NOT SUPPORTED"
      case (Main.txt: `Case "HCFA": .Range("B" & rW) = "CLAIM NOT
      SUPPORTED BY MACRO."`).

  claims_split_ub_run_batch()        — PART 2 (cps_entry.py): keys the split
      drafts into the CPS mainframe, across up to 4 emulator sessions in
      parallel, same ThreadPoolExecutor/Queue pattern as release_pend's
      release_pend_run_batch / claim_split_hcfa's claim_split_run_batch.

Needs pdfplumber / requests / beautifulsoup4 / openpyxl — already added to
requirements.txt by the claim_split_hcfa port.
"""

from __future__ import annotations

import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from queue import Queue

from rule_engine.registry import register_function
from rule_engine.functions.helpers import attach_emulator_sessions

from .cps_entry import ub_nonscratch_split, ub_scratch_not_online, ub_scratch_split
from .excel_export import write_workbook
from .pdf_backend import ClaimPdfReader
from .pdf_extract import extract_claim
from .utils import get_screen_id
from .web_claims import WebClaimsSession, get_pdf_claim_legacy


def _open_pdf_on_screen(pdf_path: str, claim_no: str) -> None:
    """Same best-effort "watch it on screen" helper as claim_split_hcfa/script.py."""
    try:
        os.startfile(pdf_path)  # noqa: S606 — Windows-only, deliberate
    except Exception as exc:
        print(f"[claims_split_ub_get_edi_details] show_pdf: couldn't open {claim_no} "
              f"({pdf_path}) on screen: {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# PART 1 — claims_split_ub_get_edi_details (web_claims.py + pdf_extract.py)
# ---------------------------------------------------------------------------

@register_function(
    name="claims_split_ub_get_edi_details",
    tag="Claims Split UB",
    color="#3f8fb5",
    inputs=[
        {"name": "dest_dir", "type": "str", "default": ""},
        {"name": "use_new_api", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "most_recent_image", "type": "str", "options": ["Y", "N"], "default": "Y"},
        {"name": "show_pdf", "type": "str", "options": ["Y", "N"], "default": "Y"},
        {"name": "show_browser", "type": "str", "options": ["Y", "N"], "default": "Y"},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "claims_df", "type": "dataframe"},
        {"name": "service_lines_df", "type": "dataframe"},
        {"name": "xlsx_path", "type": "str"},
    ],
)
def claims_split_ub_get_edi_details(
    dest_dir: str = "",
    use_new_api: str = "N",
    most_recent_image: str = "Y",
    show_pdf: str = "Y",
    show_browser: str = "Y",
    context=None,
):
    """
    Mirrors the "02.GET EDI DETAILS" branch of cmdRUN_Click. For each row in
    context['df'] (expects a CLAIM_NO column, 11 characters), fetches the
    claim's PDF and parses it. HCFA claims are reported and skipped (this
    macro only supports UB, same as the VBA's `Case "HCFA": ... "CLAIM NOT
    SUPPORTED BY MACRO."` in Main.txt).

    Runs sequentially, one claim at a time — no worker threads, same
    rationale as claim_split_hcfa's own version (the WebClaims sign-in
    handshake is easier to reason about on a single connection, and each
    claim's log output stays in order).

    Same *show_pdf*/*show_browser* semantics as claim_split_hcfa's version
    — see that module's script.py docstring.

    Writes a single .xlsx workbook (xlsx_path) to *dest_dir* with the same
    three sheets the VBA produces on its own workbook — Main / ClaimInfo /
    ClaimServiceLInes — built by excel_export.write_workbook().
    """
    print("[claims_split_ub_get_edi_details] Starting...")
    if context is None:
        return {"success": False, "claims_df": [], "service_lines_df": [], "error": "context is None"}

    df = context.get("df")
    if df is None or df.empty:
        print("[claims_split_ub_get_edi_details] WARNING: context['df'] is empty — nothing to fetch")
        return {"success": True, "claims_df": [], "service_lines_df": [], "xlsx_path": ""}

    dest_dir = dest_dir or os.environ.get("TEMP", ".")
    os.makedirs(dest_dir, exist_ok=True)
    most_recent = most_recent_image == "Y"
    web_api = use_new_api == "Y"
    show_pdf_on_screen = show_pdf == "Y"
    show_browser_window = show_browser == "Y"

    rows = [
        {k: (str(v).strip() if v is not None else "") for k, v in row.items()}
        for _, row in df.iterrows()
    ]
    print(f"[claims_split_ub_get_edi_details] {len(rows)} row(s) to fetch, use_new_api={web_api!r}")

    claims_results: list[dict] = []
    service_lines_results: list[dict] = []

    reader = ClaimPdfReader()
    web_session = WebClaimsSession(show_browser=show_browser_window) if web_api else None
    try:
        for i, row in enumerate(rows):
            claim_no = row.get("CLAIM_NO", "")
            print(f"[claims_split_ub_get_edi_details] ({i + 1}/{len(rows)}) fetching {claim_no!r}")
            claims_row = {"CLAIM_NO": claim_no, "MACRO_STATUS": "", "CLAIM_TYPE": ""}
            svl_rows: list[dict] = []
            try:
                if len(claim_no) != 11:
                    claims_row["MACRO_STATUS"] = "INVALID CLAIM NUMBER (must be 11 characters)"
                    claims_results.append(claims_row)
                    continue

                if web_api:
                    claim_type, pdf_path = web_session.fetch_claim(claim_no, dest_dir, most_recent)
                else:
                    claim_type, pdf_path = get_pdf_claim_legacy(claim_no, dest_dir, most_recent)

                if claim_type == "UB":
                    if not pdf_path or not os.path.exists(pdf_path):
                        claims_row["MACRO_STATUS"] = "CANCELLED: FILE NOT EXISTS"
                    else:
                        if show_pdf_on_screen:
                            _open_pdf_on_screen(pdf_path, claim_no)
                        extracted = extract_claim(reader, pdf_path, claim_no)
                        demographics = extracted["demographics"]
                        demographics["CLAIM_TYPE"] = "UB"
                        claims_row = demographics
                        claims_row["MACRO_STATUS"] = ""
                        svl_rows = extracted["service_lines"]
                        reader.close(pdf_path)
                        if not show_pdf_on_screen:
                            try:
                                os.remove(pdf_path)
                            except OSError:
                                pass
                elif claim_type in ("Not Found.", "CCN Missing.", ""):
                    claims_row["MACRO_STATUS"] = "CANCELLED: UNABLE TO VEIW CLAIM"
                elif claim_type == "HCFA":
                    claims_row["CLAIM_TYPE"] = "HCFA"
                    claims_row["MACRO_STATUS"] = "CANCELLED: CLAIM NOT SUPPORTED BY MACRO."
                else:
                    claims_row["MACRO_STATUS"] = f"CANCELLED: {claim_type}"
            except Exception as exc:
                print(f"[claims_split_ub_get_edi_details] error on {claim_no}: {exc}")
                traceback.print_exc()
                claims_row["MACRO_STATUS"] = f"EXCEPTION: {type(exc).__name__}: {exc}"
            claims_results.append(claims_row)
            service_lines_results.extend(svl_rows)
    finally:
        reader.close()

    print(f"[claims_split_ub_get_edi_details] Done. Fetched {len(claims_results)} claim(s), "
          f"{len(service_lines_results)} service line(s).")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx_path = ""
    try:
        xlsx_path = write_workbook(
            claims_results, service_lines_results, os.path.join(dest_dir, f"ClaimsSplitUB_{timestamp}.xlsx"),
        )
        print(f"[claims_split_ub_get_edi_details] Wrote Excel workbook: {xlsx_path}")
    except Exception as exc:
        print(f"[claims_split_ub_get_edi_details] WARNING: failed to write Excel workbook: {exc}")
        traceback.print_exc()

    return {
        "success": True,
        "claims_df": claims_results,
        "service_lines_df": service_lines_results,
        "xlsx_path": xlsx_path,
    }


# ---------------------------------------------------------------------------
# PART 2 — claims_split_ub_run_batch (cps_entry.py)
# ---------------------------------------------------------------------------

def _process_split_row(screen, claim_row: dict, demographics: dict, service_lines: list[dict],
                        split_option: str, settings: dict) -> dict:
    """
    `claim_row` and `demographics` are the SAME dict, passed twice on
    purpose — same convention as claim_split_hcfa's `_process_split_row`:
    claims_split_ub_get_edi_details() returns one flat row per claim
    carrying both the extracted PDF fields and whatever scratch-mode fields
    (NEW_CERT/NEW_CCN/NEW_DOS/NEWBORN_TYPE/NON_NEWBORN_SEQ) the caller adds
    to claims_df afterward.
    """
    claim_no = claim_row.get("CLAIM_NO", "")
    if claim_row.get("CLAIM_TYPE", "").upper() != "UB":
        return {"CLAIM_NO": claim_no, "MACRO_STATUS": "SKIPPED: not a UB claim"}

    try:
        if split_option == "SCRATCH":
            new_dos = claim_row.get("NEW_DOS", "")
            if not new_dos:
                return {"CLAIM_NO": claim_no, "MACRO_STATUS": "CANCELLED: NEW DOS IS REQUIRED."}
            result = ub_scratch_split(
                screen, claim_no, claim_row.get("NEW_CCN", ""), claim_row.get("NEW_CERT", ""),
                new_dos, claim_row, demographics, service_lines, settings,
            )
        elif split_option == "SCRATCH NOT ONLINE":
            new_dos = claim_row.get("NEW_DOS", "")
            if not new_dos:
                return {"CLAIM_NO": claim_no, "MACRO_STATUS": "CANCELLED: NEW DOS IS REQUIRED."}
            result = ub_scratch_not_online(
                screen, claim_no, claim_row.get("NEW_CCN", ""), claim_row.get("NEW_CERT", ""),
                new_dos, claim_row, demographics, service_lines, settings,
            )
        elif split_option == "NON SCRATCH":
            result = ub_nonscratch_split(screen, claim_row, service_lines, settings)
        else:
            return {"CLAIM_NO": claim_no, "MACRO_STATUS": f"SKIPPED: unknown split option {split_option!r}"}
    except Exception as exc:
        print(f"[{claim_no}] EXCEPTION during split: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return {"CLAIM_NO": claim_no, "MACRO_STATUS": f"EXCEPTION: {type(exc).__name__}: {exc}"}

    status = f"{result['status']} {result['notes']}".strip()
    return {"CLAIM_NO": claim_no, "MACRO_STATUS": status, "DRAFTS_CREATED": result["drafts_created"]}


@register_function(
    name="claims_split_ub_run_batch",
    tag="Claims Split UB",
    color="#3f8fb5",
    inputs=[
        {"name": "split_option", "type": "str", "options": ["SCRATCH", "SCRATCH NOT ONLINE", "NON SCRATCH"], "default": "NON SCRATCH"},
        {"name": "split_grouping", "type": "str", "options": ["BY DATE OF SERVICE", "NONE"], "default": "BY DATE OF SERVICE"},
        {"name": "two_lines_per_draft", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "get_cps_discount", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "inel_remove_mode", "type": "str",
         "options": ["", "REMOVE ALL EXISTING INEL", "REMOVE EXISTING INEL1", "REMOVE EXISTING INEL2"], "default": ""},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "result", "type": "list"},
    ],
)
def claims_split_ub_run_batch(
    split_option: str = "NON SCRATCH",
    split_grouping: str = "BY DATE OF SERVICE",
    two_lines_per_draft: str = "N",
    get_cps_discount: str = "N",
    inel_remove_mode: str = "",
    context=None,
):
    """
    Mirrors the "03.SPLIT CLAIM" branch of cmdRUN_Click. Expects
    context['claims_df'] and context['service_lines_df'] — normally chained
    straight from claims_split_ub_get_edi_details()'s outputs. Only rows
    with CLAIM_TYPE == "UB" are split (same gate as
    `.Range("D" & rW) <> "UB"` in the VBA). Runs across up to 4 emulator
    sessions in parallel, same pattern as claim_split_hcfa's
    claim_split_run_batch.

    Unlike claim_split_hcfa, this macro's MAIN X3 grouping dropdown has no
    "BY DIAGNOSIS" branch in the VBA at all — `split_grouping` only ever
    changes behavior when set to "BY DATE OF SERVICE" (see cps_entry.py).
    """
    print("[claims_split_ub_run_batch] Starting...")
    if context is None:
        return {"success": False, "result": [], "error": "context is None"}

    claims = context.get("claims_df")
    service_lines = context.get("service_lines_df") or []
    if not claims:
        print("[claims_split_ub_run_batch] WARNING: context['claims_df'] is empty — nothing to split")
        return {"success": True, "result": []}

    settings = {
        "split_grouping": split_grouping,
        "two_lines_per_draft": two_lines_per_draft,
        "get_cps_discount": get_cps_discount,
        "inel_remove_mode": inel_remove_mode,
    }

    lines_by_claim: dict[str, list[dict]] = {}
    for svl in service_lines:
        lines_by_claim.setdefault(svl.get("CLAIM_NO", ""), []).append(svl)

    try:
        sessions = attach_emulator_sessions(n=4)
        print(f"[claims_split_ub_run_batch] Attached {len(sessions)} emulator session(s). "
              f"Initial screen on session 1: {get_screen_id(sessions[0].Screen)!r}")
    except Exception as exc:
        print(f"[claims_split_ub_run_batch] ERROR connecting to emulator: {exc}")
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"Emulator connection failed: {exc}"}

    worker_count = min(4, len(sessions))
    print(f"[claims_split_ub_run_batch] Using {worker_count} emulator session(s) for {len(claims)} claim(s).")

    indexed_rows = list(enumerate(claims))
    buckets = [indexed_rows[i::worker_count] for i in range(worker_count)]
    out_q: Queue = Queue()

    def _worker(worker_idx: int, items: list[tuple[int, dict]]):
        import pythoncom
        pythoncom.CoInitialize()
        try:
            screen = sessions[worker_idx].Screen
            try:
                screen.WaitHostQuiet(2000)
            except Exception:
                pass
            for pos, claim_row in items:
                claim_no = claim_row.get("CLAIM_NO", "")
                own_lines = [dict(svl) for svl in lines_by_claim.get(claim_no, [])]
                try:
                    res = _process_split_row(screen, claim_row, claim_row, own_lines, split_option, settings)
                except Exception as exc:
                    print(f"[claims_split_ub_run_batch] Worker {worker_idx} error on {claim_no}: {exc}")
                    traceback.print_exc()
                    res = {"CLAIM_NO": claim_no, "MACRO_STATUS": f"EXCEPTION: {type(exc).__name__}: {exc}"}
                out_q.put((pos, res))
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for i in range(worker_count):
            pool.submit(_worker, i, buckets[i])

        results: list = [None] * len(claims)
        collected = 0
        while collected < len(claims):
            pos, res = out_q.get()
            results[pos] = res
            collected += 1

    print(f"[claims_split_ub_run_batch] Done. Processed {len(results)}/{len(claims)} claim(s).")
    return {"success": True, "result": results}


# ---------------------------------------------------------------------------
# claims_split_ub_export_excel — re-export the Main/ClaimInfo/ClaimServiceLInes
# workbook after "03.SPLIT CLAIM" has run, with each claim's MACRO_STATUS
# updated to reflect the split result rather than just the EDI fetch.
# ---------------------------------------------------------------------------

@register_function(
    name="claims_split_ub_export_excel",
    tag="Claims Split UB",
    color="#3f8fb5",
    inputs=[{"name": "dest_dir", "type": "str", "default": ""}],
    outputs=[{"name": "success", "type": "bool"}, {"name": "xlsx_path", "type": "str"}],
)
def claims_split_ub_export_excel(dest_dir: str = "", context=None):
    """
    Chain this after claims_split_ub_run_batch() to get a workbook whose
    MACRO STATUS column reflects the split outcome, instead of only the
    "02.GET EDI DETAILS" status. Safe to call on its own right after
    claims_split_ub_get_edi_details too — context['result'] simply won't be
    there yet.
    """
    print("[claims_split_ub_export_excel] Starting...")
    if context is None:
        return {"success": False, "xlsx_path": "", "error": "context is None"}

    claims = context.get("claims_df") or []
    service_lines = context.get("service_lines_df") or []
    split_results = context.get("result") or []

    if not claims:
        print("[claims_split_ub_export_excel] WARNING: context['claims_df'] is empty — nothing to export")
        return {"success": True, "xlsx_path": ""}

    split_by_claim = {r.get("CLAIM_NO", ""): r for r in split_results}
    export_claims = []
    for claim in claims:
        row = dict(claim)
        split_row = split_by_claim.get(row.get("CLAIM_NO", ""))
        if split_row:
            row["MACRO_STATUS"] = split_row.get("MACRO_STATUS", row.get("MACRO_STATUS", ""))
        export_claims.append(row)

    dest_dir = dest_dir or os.environ.get("TEMP", ".")
    os.makedirs(dest_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    xlsx_path = write_workbook(export_claims, service_lines, os.path.join(dest_dir, f"ClaimsSplitUB_{timestamp}.xlsx"))
    print(f"[claims_split_ub_export_excel] Wrote Excel workbook: {xlsx_path}")

    return {"success": True, "xlsx_path": xlsx_path}
