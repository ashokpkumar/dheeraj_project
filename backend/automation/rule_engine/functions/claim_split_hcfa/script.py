"""
Claim Split HCFA — main registered functions.

Ports Main.txt's two real actions ("02.GET EDI DETAILS" and "03.SPLIT
CLAIM" — "01.CLEAN ALL SHEETS" doesn't apply here, there's no worksheet to
clear) as two separate `@register_function` entries, same convention as
release_pend_macro/script.py:

  claim_split_get_edi_details()  — PART 1 (web_claims.py + pdf_extract.py):
      fetches each claim's PDF from the web and parses it into two
      DataFrames, mirroring the VBA's two-sheet split (ClaimInfo /
      ClaimServiceLInes). Pure I/O — no emulator session needed.

  claim_split_run_batch()        — PART 2 (cps_entry.py): keys the split
      drafts into the CPS mainframe, across up to 4 emulator sessions in
      parallel, same ThreadPoolExecutor/Queue pattern as release_pend's
      release_pend_run_batch.

Needs pdfplumber / requests / beautifulsoup4 added to requirements.txt (not
there yet — see the repo root README or ask before deploying).
"""

from __future__ import annotations

import csv
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from rule_engine.registry import register_function
from rule_engine.functions.helpers import attach_emulator_sessions

from .cps_entry import (
    hcfa_nonscratch_split, hcfa_pos_collection, hcfa_scratch_not_online, hcfa_scratch_split,
)
from .pdf_backend import ClaimPdfReader
from .pdf_extract import extract_claim
from .utils import get_screen_id
from .web_claims import WebClaimsSession, get_pdf_claim_legacy


# ---------------------------------------------------------------------------
# PART 1 — claim_split_get_edi_details (web_claims.py + pdf_extract.py)
# ---------------------------------------------------------------------------

@register_function(
    name="claim_split_get_edi_details",
    tag="Claim Split HCFA",
    color="#6a3fb5",
    inputs=[
        {"name": "dest_dir", "type": "str", "default": ""},
        {"name": "use_new_api", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "most_recent_image", "type": "str", "options": ["Y", "N"], "default": "Y"},
        {"name": "max_workers", "type": "int", "default": 4},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "claims_df", "type": "dataframe"},
        {"name": "service_lines_df", "type": "dataframe"},
    ],
)
def claim_split_get_edi_details(
    dest_dir: str = "",
    use_new_api: str = "N",
    most_recent_image: str = "Y",
    max_workers: int = 4,
    context=None,
):
    """
    Mirrors the "02.GET EDI DETAILS" branch of cmdRun_Click. For each row in
    context['df'] (expects a CLAIM_NO column, 11 characters), fetches the
    claim's repriced PDF and parses it. UB claims are reported and skipped
    (this macro only supports HCFA, same as the VBA — see the "UB CLAIM NOT
    SUPPORTED BY THIS MACRO." case in Main.txt).
    """
    print("[claim_split_get_edi_details] Starting...")
    if context is None:
        return {"success": False, "claims_df": [], "service_lines_df": [], "error": "context is None"}

    df = context.get("df")
    if df is None or df.empty:
        print("[claim_split_get_edi_details] WARNING: context['df'] is empty — nothing to fetch")
        return {"success": True, "claims_df": [], "service_lines_df": []}

    dest_dir = dest_dir or os.environ.get("TEMP", ".")
    os.makedirs(dest_dir, exist_ok=True)
    most_recent = most_recent_image == "Y"
    web_api = use_new_api == "Y"

    rows = [
        {k: (str(v).strip() if v is not None else "") for k, v in row.items()}
        for _, row in df.iterrows()
    ]
    print(f"[claim_split_get_edi_details] {len(rows)} row(s) to fetch, use_new_api={web_api!r}")

    out_q: Queue = Queue()

    def _worker(worker_idx: int, items: list[tuple[int, dict]]):
        reader = ClaimPdfReader()
        web_session = WebClaimsSession() if web_api else None
        try:
            for pos, row in items:
                claim_no = row.get("CLAIM_NO", "")
                claims_row = {"CLAIM_NO": claim_no, "MACRO_STATUS": "", "CLAIM_TYPE": ""}
                svl_rows: list[dict] = []
                try:
                    if len(claim_no) != 11:
                        claims_row["MACRO_STATUS"] = "INVALID CLAIM NUMBER (must be 11 characters)"
                        out_q.put((pos, claims_row, svl_rows))
                        continue

                    if web_api:
                        claim_type, pdf_path = web_session.fetch_claim(claim_no, dest_dir, most_recent)
                    else:
                        claim_type, pdf_path = get_pdf_claim_legacy(claim_no, dest_dir, most_recent)

                    if claim_type == "UB":
                        claims_row["CLAIM_TYPE"] = "UB"
                        claims_row["MACRO_STATUS"] = "CANCELLED: UB CLAIM NOT SUPPORTED BY THIS MACRO."
                    elif not pdf_path or not os.path.exists(pdf_path):
                        claims_row["MACRO_STATUS"] = f"CANCELLED: {claim_type or 'FILE NOT EXISTS'}"
                    else:
                        claims_row["CLAIM_TYPE"] = "HCFA"
                        extracted = extract_claim(reader, pdf_path, claim_no)
                        demographics = extracted["demographics"]
                        demographics["CLAIM_TYPE"] = "HCFA"
                        claims_row = demographics
                        claims_row["MACRO_STATUS"] = ""
                        svl_rows = extracted["service_lines"]
                        reader.close(pdf_path)
                        try:
                            os.remove(pdf_path)
                        except OSError:
                            pass
                except Exception as exc:
                    print(f"[claim_split_get_edi_details] Worker {worker_idx} error on {claim_no}: {exc}")
                    traceback.print_exc()
                    claims_row["MACRO_STATUS"] = f"EXCEPTION: {type(exc).__name__}: {exc}"
                out_q.put((pos, claims_row, svl_rows))
        finally:
            reader.close()

    worker_count = max(1, int(max_workers))
    buckets = [[] for _ in range(worker_count)]
    for pos, row in enumerate(rows):
        buckets[pos % worker_count].append((pos, row))

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for i in range(worker_count):
            pool.submit(_worker, i, buckets[i])

        claims_results: list = [None] * len(rows)
        service_lines_results: list[dict] = []
        collected = 0
        while collected < len(rows):
            pos, claims_row, svl_rows = out_q.get()
            claims_results[pos] = claims_row
            service_lines_results.extend(svl_rows)
            collected += 1

    print(f"[claim_split_get_edi_details] Done. Fetched {len(claims_results)} claim(s), "
          f"{len(service_lines_results)} service line(s).")
    return {"success": True, "claims_df": claims_results, "service_lines_df": service_lines_results}


# ---------------------------------------------------------------------------
# PART 2 — claim_split_run_batch (cps_entry.py)
# ---------------------------------------------------------------------------

def _load_pos_reference(path: str) -> dict:
    """Loads the REFERENCE sheet's (HCA POS, CPS POS) pairs from a 2-column CSV."""
    if not path or not os.path.exists(path):
        return {}
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) >= 2:
                rows.append((row[0], row[1]))
    return hcfa_pos_collection(rows)


def _process_split_row(screen, claim_row: dict, demographics: dict, service_lines: list[dict],
                        split_option: str, settings: dict, pos_reference: dict) -> dict:
    """
    `claim_row` and `demographics` are typically the SAME dict, passed
    twice on purpose: claim_split_get_edi_details() returns one flat row
    per claim carrying both the extracted PDF fields (INSURED_ID, DX_A..L,
    BILLING_*, etc. — what cps_entry.py calls `demographics`) and whatever
    scratch-mode fields (NEW_CERT/NEW_CCN/NEW_DOS/NEWBORN_TYPE/
    NON_NEWBORN_SEQ) the caller adds to claims_df afterward — mirroring how
    the VBA kept both on the same MAIN sheet row, just different columns.
    """
    claim_no = claim_row.get("CLAIM_NO", "")
    if claim_row.get("CLAIM_TYPE", "").upper() != "HCFA":
        return {"CLAIM_NO": claim_no, "MACRO_STATUS": "SKIPPED: not an HCFA claim"}

    try:
        if split_option == "SCRATCH":
            new_dos = claim_row.get("NEW_DOS", "")
            if not new_dos:
                return {"CLAIM_NO": claim_no, "MACRO_STATUS": "CANCELLED: NEW DATE OF SERVICE REQUIRED"}
            result = hcfa_scratch_split(
                screen, claim_no, claim_row.get("NEW_CCN", ""), claim_row.get("NEW_CERT", ""),
                new_dos, claim_row, demographics, service_lines, settings,
            )
        elif split_option == "SCRATCH NOT ONLINE":
            new_dos = claim_row.get("NEW_DOS", "")
            if not new_dos:
                return {"CLAIM_NO": claim_no, "MACRO_STATUS": "CANCELLED: NEW DATE OF SERVICE REQUIRED"}
            result = hcfa_scratch_not_online(
                screen, claim_no, claim_row.get("NEW_CCN", ""), claim_row.get("NEW_CERT", ""),
                new_dos, claim_row, demographics, service_lines, pos_reference, settings,
            )
        elif split_option == "NON SCRATCH":
            result = hcfa_nonscratch_split(screen, claim_row, service_lines, settings)
        else:
            return {"CLAIM_NO": claim_no, "MACRO_STATUS": f"SKIPPED: unknown split option {split_option!r}"}
    except Exception as exc:
        print(f"[{claim_no}] EXCEPTION during split: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return {"CLAIM_NO": claim_no, "MACRO_STATUS": f"EXCEPTION: {type(exc).__name__}: {exc}"}

    status = f"{result['status']} {result['notes']}".strip()
    return {"CLAIM_NO": claim_no, "MACRO_STATUS": status, "DRAFTS_CREATED": result["drafts_created"]}


@register_function(
    name="claim_split_run_batch",
    tag="Claim Split HCFA",
    color="#6a3fb5",
    inputs=[
        {"name": "split_option", "type": "str", "options": ["SCRATCH", "SCRATCH NOT ONLINE", "NON SCRATCH"], "default": "NON SCRATCH"},
        {"name": "split_grouping", "type": "str", "options": ["BY DATE OF SERVICE", "BY DIAGNOSIS"], "default": "BY DATE OF SERVICE"},
        {"name": "two_lines_per_draft", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "get_cps_discount", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "bypass", "type": "str", "options": ["Y", "N"], "default": "N"},
        {"name": "pos_reference_path", "type": "str", "default": ""},
    ],
    outputs=[
        {"name": "success", "type": "bool"},
        {"name": "result", "type": "list"},
    ],
)
def claim_split_run_batch(
    split_option: str = "NON SCRATCH",
    split_grouping: str = "BY DATE OF SERVICE",
    two_lines_per_draft: str = "N",
    get_cps_discount: str = "N",
    bypass: str = "N",
    pos_reference_path: str = "",
    context=None,
):
    """
    Mirrors the "03.SPLIT CLAIM" branch of cmdRun_Click. Expects
    context['claims_df'] and context['service_lines_df'] — normally chained
    straight from claim_split_get_edi_details()'s outputs. Only rows with
    CLAIM_TYPE == "HCFA" are split (same gate as `.Range("D" & rW) <> "HCFA"`
    in the VBA). Runs across up to 4 emulator sessions in parallel, same
    pattern as release_pend_macro's release_pend_run_batch.
    """
    print("[claim_split_run_batch] Starting...")
    if context is None:
        return {"success": False, "result": [], "error": "context is None"}

    claims = context.get("claims_df")
    service_lines = context.get("service_lines_df") or []
    if not claims:
        print("[claim_split_run_batch] WARNING: context['claims_df'] is empty — nothing to split")
        return {"success": True, "result": []}

    settings = {
        "split_grouping": split_grouping,
        "two_lines_per_draft": two_lines_per_draft,
        "get_cps_discount": get_cps_discount,
        "bypass": bypass,
    }
    pos_reference = _load_pos_reference(pos_reference_path)

    # Group service lines by claim number once, up front.
    lines_by_claim: dict[str, list[dict]] = {}
    for svl in service_lines:
        lines_by_claim.setdefault(svl.get("CLAIM_NO", ""), []).append(svl)

    try:
        sessions = attach_emulator_sessions(n=4)
        print(f"[claim_split_run_batch] Attached {len(sessions)} emulator session(s). "
              f"Initial screen on session 1: {get_screen_id(sessions[0].Screen)!r}")
    except Exception as exc:
        print(f"[claim_split_run_batch] ERROR connecting to emulator: {exc}")
        traceback.print_exc()
        return {"success": False, "result": [], "error": f"Emulator connection failed: {exc}"}

    worker_count = min(4, len(sessions))
    print(f"[claim_split_run_batch] Using {worker_count} emulator session(s) for {len(claims)} claim(s).")

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
                    res = _process_split_row(screen, claim_row, claim_row, own_lines, split_option, settings, pos_reference)
                except Exception as exc:
                    print(f"[claim_split_run_batch] Worker {worker_idx} error on {claim_no}: {exc}")
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

    print(f"[claim_split_run_batch] Done. Processed {len(results)}/{len(claims)} claim(s).")
    return {"success": True, "result": results}
