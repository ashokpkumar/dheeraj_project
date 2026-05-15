"""
Windows Automation Service
===========================

Standalone service that runs ONLY on Windows and handles all emulator operations.
Exposes a simple HTTP API for Linux-based systems to request emulator work.

Run this on Windows with:
    python windows_automation_service.py

The service will listen on http://localhost:5555 by default.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
from queue import Queue

# Windows-only: requires pywin32
try:
    import win32com.client  # pywin32
    import pythoncom
except ImportError:
    raise ImportError(
        "This service requires pywin32. Install with: pip install pywin32\n"
        "Run this service ONLY on Windows machines."
    )

# ─────────────────────────────────────────────────────────────
# Configure logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Flask app setup
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# Configuration
SERVICE_PORT = int(os.getenv('WINDOWS_SERVICE_PORT', 5555))
SERVICE_HOST = os.getenv('WINDOWS_SERVICE_HOST', '0.0.0.0')
HOST_SETTLE_TIME_MS = int(os.getenv('HOST_SETTLE_TIME_MS', 100))

# ─────────────────────────────────────────────────────────────
# Emulator Helper Functions (moved from helpers.py)
# ─────────────────────────────────────────────────────────────

def clean_name(nm: str) -> str:
    """Clean and normalize name field."""
    parts = [p.strip() for p in (nm or "").split(" ") if p.strip()]
    return " ".join(parts)


def _wait_ready(screen) -> None:
    """Wait until OIA.Xstatus == 0 (host ready)."""
    import time
    while screen.OIA.Xstatus != 0:
        time.sleep(HOST_SETTLE_TIME_MS / 1000.0)


def _move_to(screen, r: int, c: int) -> None:
    """Move cursor to row, column."""
    _wait_ready(screen)
    screen.MoveTo(r, c)
    _wait_ready(screen)


def send_enter(screen) -> None:
    """Send ENTER key."""
    screen.SendKeys("<Enter>")
    _wait_ready(screen)


def send_pf(screen, n: int) -> None:
    """Send PF (program function) key."""
    screen.SendKeys(f"<PF{n}>")
    _wait_ready(screen)


def send_erase_eof(screen) -> None:
    """Send Erase-to-End-of-Field key."""
    screen.SendKeys("<EraseEOF>")
    _wait_ready(screen)


def place_value(screen, val: str, r: int, c: int) -> None:
    """Place a value on screen at row, column."""
    if val is None:
        return
    val = str(val).strip()
    if not val:
        return
    _move_to(screen, r, c)
    send_erase_eof(screen)
    screen.PutString(val, r, c)


def remove_value(screen, r: int, c: int) -> None:
    """Remove/clear value at row, column."""
    _move_to(screen, r, c)
    send_erase_eof(screen)


def get_string(screen, r: int, c: int, length: int) -> str:
    """Get string from screen at row, column."""
    _wait_ready(screen)
    return str(screen.GetString(r, c, length)).strip()


def get_screen_id(screen) -> str:
    """Get the screen ID (CPS850.01, etc)."""
    try:
        return get_string(screen, 1, 2, 10).upper()
    except Exception:
        return ""


def rtn_patient_seq_no(screen, seq_no: str) -> int:
    """
    Attempt to find the row for a patient sequence number on the listing screen.
    Returns the row number if found, else 0.
    """
    seq_no = (seq_no or "").strip()
    if not seq_no:
        return 0

    while True:
        try:
            marker = get_string(screen, 9, 2, 70)
        except Exception:
            marker = ""

        for r in range(9, 24, 2):
            try:
                cell = get_string(screen, r, 2, 2)
            except Exception:
                cell = ""
            if cell and cell == seq_no:
                return r

        send_pf(screen, 11)
        try:
            marker2 = get_string(screen, 9, 2, 70)
        except Exception:
            marker2 = ""

        if marker == marker2:
            return 0


# ─────────────────────────────────────────────────────────────
# Field Reading Routines
# ─────────────────────────────────────────────────────────────

def read_cps850_fields(screen) -> dict:
    """Read CPS850 screen fields."""
    out = {}
    out["EMPLOYEE"] = clean_name(get_string(screen, 2, 7, 37))
    out["SSN"] = get_string(screen, 3, 72, 9)
    out["CERT"] = get_string(screen, 2, 72, 9)
    out["MBR ID"] = get_string(screen, 3, 50, 8)
    out["MBR OPI"] = get_string(screen, 2, 2, 4)
    out["OPI2"] = get_string(screen, 3, 2, 4)
    out["CUSTOMER"] = get_string(screen, 6, 50, 26)
    out["PLAN #"] = get_string(screen, 7, 50, 12)
    out["EE EFF DT"] = get_string(screen, 6, 16, 6)
    out["EE TERM DT"] = get_string(screen, 6, 29, 6)
    out["EE CLASS"] = get_string(screen, 6, 6, 3)
    out["EE STATUS"] = get_string(screen, 6, 13, 2)
    out["DEP EFF DT"] = get_string(screen, 7, 16, 6)
    out["DEP TERM DT"] = get_string(screen, 7, 29, 6)
    out["DEP CLASS"] = get_string(screen, 7, 6, 3)
    out["WORK STATUS"] = get_string(screen, 4, 51, 2)
    out["PAID THRU DT"] = get_string(screen, 8, 7, 6)
    out["EE REPORTING"] = ""
    out["CSR NOTE"] = get_string(screen, 9, 2, 58) + "\n" + get_string(screen, 10, 2, 58)
    out["DATE OF BIRTH"] = get_string(screen, 2, 55, 6)
    out["EFFECTIVE DATE"] = get_string(screen, 13, 40, 6)
    out["REL"] = get_string(screen, 13, 60, 2)
    out["TERM DATE"] = get_string(screen, 13, 50, 6)
    out["CONTINUING COV"] = get_string(screen, 6, 36, 1)
    out["DATE"] = ""
    out["WAITING PERIOD"] = ""
    out["MARITAL STATUS"] = get_string(screen, 2, 65, 1)
    out["CLAIM PND IND"] = get_string(screen, 13, 79, 2)
    out["PRE-EX MET DT"] = ""
    out["FLEX ROLLOVER"] = ""
    out["PAY EMPLOYEE"] = ""
    out["ALTERNATE ADDRESS"] = ""
    out["PROVIDER NAME"] = get_string(screen, 14, 6, 29)
    out["BILLING NAME"] = get_string(screen, 1, 39, 31)
    out["TAX ID"] = get_string(screen, 14, 40, 9)
    out["OPI"] = get_string(screen, 15, 59, 5)
    out["ADDRESS"] = get_string(screen, 3, 7, 38) + "\n" + get_string(screen, 4, 7, 38)
    out["CITY"] = get_string(screen, 5, 6, 20)
    out["STATE"] = get_string(screen, 5, 27, 2)
    out["ZIP"] = get_string(screen, 5, 30, 12)
    out["EE DOB"] = get_string(screen, 2, 55, 6)
    out["LOCATION"] = get_string(screen, 5, 50, 4)
    out["EE TERM STAT"] = get_string(screen, 6, 26, 2)
    out["MBR ORG EFF DT"] = get_string(screen, 6, 45, 4)
    out["CONTINUING COVERAGE"] = get_string(screen, 6, 36, 1)
    out["DEP STATUS"] = get_string(screen, 7, 13, 2)
    out["POLICY EFF DT"] = get_string(screen, 8, 53, 6)
    out["DEP TERM STATUS"] = get_string(screen, 7, 26, 2)
    out[" TERM DATE"] = get_string(screen, 8, 64, 7)
    out["DEV COV STATUS"] = get_string(screen, 7, 42, 7)
    out["MENTAL VENDOR"] = get_string(screen, 8, 77, 4)
    out["FLEX"] = ""
    out["PRE-EX MOS"] = get_string(screen, 7, 79, 2)
    out["PRE-CERT"] = get_string(screen, 4, 78, 3)
    out["ROLLOVER"] = ""
    out["PRE-EXISTING"] = get_string(screen, 6, 80, 1)
    out["FAMILY COVERAGE"] = get_string(screen, 12, 2, 3)
    out["UPDATED"] = get_string(screen, 12, 6, 6)
    out["OTH INS TYPE"] = get_string(screen, 11, 27, 2)
    out["LAST UPDATE DATE"] = get_string(screen, 11, 20, 6)
    out["OTH INS EFF DT"] = get_string(screen, 11, 30, 6)
    out["OTH INS TERM DT"] = get_string(screen, 11, 37, 6)
    out["PROVIDER"] = get_string(screen, 14, 6, 29)
    out["BILLING NM"] = get_string(screen, 1, 39, 31)
    out[" ADDRESS"] = get_string(screen, 15, 2, 25)
    out[" CITY"] = get_string(screen, 15, 28, 12)
    out[" STATE"] = get_string(screen, 15, 41, 2)
    out[" ZIP"] = get_string(screen, 15, 44, 10)
    out["PHONE"] = get_string(screen, 14, 59, 13)
    out[" TAX ID"] = get_string(screen, 14, 40, 9)
    out["PCP"] = get_string(screen, 20, 69, 12)
    out[" OPI"] = get_string(screen, 15, 59, 5)
    out["SPECIALTY"] = get_string(screen, 19, 70, 3)
    out["TIER"] = get_string(screen, 19, 79, 2)
    out["RATE"] = get_string(screen, 17, 70, 11)
    out["FINANCIAL INVESTIGATION"] = get_string(screen, 18, 70, 11)
    out["TAXONOMY"] = ""
    out["PROVIDER NOTE"] = (
        get_string(screen, 16, 2, 62) + "\n" +
        get_string(screen, 17, 2, 62) + "\n" +
        get_string(screen, 18, 2, 62) + "\n" +
        get_string(screen, 19, 2, 62)
    )
    return out


def read_blx2460_fields(screen) -> dict:
    """Read BLX2460 screen fields."""
    return {
        "UB/HCFA AFV FIELD": get_string(screen, 23, 13, 1),
        "UB/HCFA CONDITION NOTE": get_string(screen, 22, 44, 36),
        "UB TOB": get_string(screen, 2, 54, 3),
    }


def read_cps450_fields(screen) -> dict:
    """Read CPS450 screen fields."""
    return {
        "UB/HCFA AFV FIELD": get_string(screen, 3, 15, 1),
        "UB/HCFA CONDITION NOTE": get_string(screen, 3, 46, 35),
        "UB TOB": get_string(screen, 2, 54, 3),
        "HCFA AP CODE": get_string(screen, 5, 68, 2),
        "HCFA CFV FIELD": get_string(screen, 3, 17, 1),
    }


def read_cps310_fields(screen) -> dict:
    """Read CPS310 screen fields."""
    return {
        "PROVIDER ": get_string(screen, 3, 2, 28),
        "ADDRESS ": get_string(screen, 4, 2, 28),
        "CITY ": get_string(screen, 6, 2, 23),
        "STATE ": get_string(screen, 6, 26, 3),
        "ZIP ": get_string(screen, 6, 30, 11),
    }


def process_claim(
    screen,
    claim_id: str,
    method: str,
    cert_date_mmddyy: str,
    seq_no: str,
    dental_flag: bool
) -> dict:
    """
    Reproduces the GET_INFORMATION flow for a single claim.
    Returns a dict with business-named fields and a MACRO STATUS.
    """
    result = {
        "CLAIM CONTROL #": claim_id,
        "BG SV DT": "",
        "PATIENT SEQ NO ##": "",
        "MACRO STATUS": ""
    }

    try:
        send_pf(screen, 9)
        max_steps = 500
        steps = 0

        while steps < max_steps:
            steps += 1
            _wait_ready(screen)
            sid = get_screen_id(screen)

            if sid == "CPS520.01":
                if method.upper() == "SEARCH BY CCN":
                    place_value(screen, claim_id, 8, 15)
                elif method.upper() == "SEARCH BY CERT":
                    place_value(screen, claim_id, 9, 15)
                if cert_date_mmddyy:
                    place_value(screen, cert_date_mmddyy, 12, 15)
                if dental_flag:
                    place_value(screen, "D", 9, 59)
                send_enter(screen)

                if get_screen_id(screen) == "CPS520.01":
                    result["MACRO STATUS"] = (
                        get_string(screen, 31, 2, 70) + " " +
                        get_string(screen, 30, 2, 70)
                    )
                    break

            elif sid == "CPS215.01":
                send_enter(screen)
            elif sid == "CPS125.01":
                result["MACRO STATUS"] = "MEMBER RECORD NOT FOUND"
                break
            elif sid == "CPS220.01":
                ln_row = rtn_patient_seq_no(screen, (seq_no or "00"))
                if ln_row != 0:
                    screen.PutString((seq_no or "00"), 2, 6)
                    send_enter(screen)
                else:
                    result["MACRO STATUS"] = "UNABLE TO IDENTIFY SEQ NO"
                    break
            elif sid == "CPS325.01":
                send_pf(screen, 8)
                place_value(screen, "850", 2, 37)
                send_enter(screen)
            elif sid == "CPS500.01":
                send_enter(screen)
            elif sid == "CPS850.01":
                result.update(read_cps850_fields(screen))
                if method.upper() == "SEARCH BY CERT":
                    break
                if dental_flag:
                    break
                send_enter(screen)
            elif sid == "CPS228.01":
                send_enter(screen)
            elif sid == "CPS920.01":
                send_enter(screen)
            elif sid == "BLX2460.01":
                result.update(read_blx2460_fields(screen))
                send_pf(screen, 8)
            elif sid == "CPS450.01":
                result.update(read_cps450_fields(screen))
                send_pf(screen, 8)
            elif sid == "CPS511.01":
                place_value(screen, "310", 2, 37)
                send_enter(screen)
            elif sid == "CPS310.01":
                result.update(read_cps310_fields(screen))
                break
            else:
                result["MACRO STATUS"] = "UNEXPECTED SCREEN MAPPING ERROR."
                break

        send_pf(screen, 9)
        result["MACRO STATUS"] = f"DONE.{result.get('MACRO STATUS', '')}"
        return result

    except Exception as e:
        logger.error(f"Error processing claim {claim_id}: {e}")
        result["MACRO STATUS"] = f"ERROR: {str(e)}"
        return result


def attach_emulator_sessions(n: int = 4) -> list:
    """
    Attach to up to `n` already-open EXTRA emulator sessions and return them as a list.
    Requires pythoncom.CoInitialize() in the calling thread.
    """
    system = win32com.client.Dispatch("EXTRA.System")
    sessions = system.Sessions
    
    if sessions.Count < 1:
        raise RuntimeError("No active emulator sessions found.")

    # 1-based collection
    result = [sessions.Item(i) for i in range(1, min(n, sessions.Count) + 1)]

    # Optional: give host a moment to be quiet
    for s in result:
        try:
            s.Screen.WaitHostQuiet(2000)
        except Exception:
            pass

    return result


# ─────────────────────────────────────────────────────────────
# HTTP API Endpoints
# ─────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'windows_automation'}), 200


@app.route('/scrap-claims', methods=['POST'])
def scrap_claims_endpoint():
    """
    Scrap claims from emulator.
    
    Request JSON:
    {
        "claim_ids": ["claim1", "claim2", ...],
        "method": "SEARCH BY CCN",  # or "SEARCH BY CERT"
        "cert_date_mmddyy": "010120",
        "seq_no": "00",
        "dental_flag": false
    }
    
    Response:
    {
        "status": "success",
        "results": [
            {
                "CLAIM CONTROL #": "...",
                "MACRO STATUS": "...",
                ... other fields ...
            },
            ...
        ]
    }
    """
    try:
        data = request.get_json()
        claim_ids = data.get('claim_ids', [])
        method = data.get('method', 'SEARCH BY CCN')
        cert_date = data.get('cert_date_mmddyy')
        seq_no = data.get('seq_no', '00')
        dental_flag = data.get('dental_flag', False)

        if not claim_ids:
            return jsonify({'status': 'error', 'message': 'No claim_ids provided'}), 400

        logger.info(f"Processing {len(claim_ids)} claims...")

        # Initialize COM for this thread
        pythoncom.CoInitialize()
        
        try:
            sessions = attach_emulator_sessions(n=4)
            worker_count = min(4, len(sessions))
            
            logger.info(f"Using {worker_count} emulator session(s)")

            # Process claims
            results = []
            for claim_id in claim_ids:
                screen = sessions[0].Screen
                result = process_claim(
                    screen=screen,
                    claim_id=claim_id,
                    method=method,
                    cert_date_mmddyy=cert_date,
                    seq_no=seq_no,
                    dental_flag=dental_flag
                )
                results.append(result)

            return jsonify({
                'status': 'success',
                'count': len(results),
                'results': results
            }), 200

        finally:
            pythoncom.CoUninitialize()

    except Exception as e:
        logger.error(f"Error scraping claims: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/process-claim', methods=['POST'])
def process_claim_endpoint():
    """
    Process a single claim.
    
    Request JSON:
    {
        "claim_id": "123456",
        "method": "SEARCH BY CCN",
        "cert_date_mmddyy": "010120",
        "seq_no": "00",
        "dental_flag": false
    }
    """
    try:
        data = request.get_json()
        claim_id = data.get('claim_id')
        method = data.get('method', 'SEARCH BY CCN')
        cert_date = data.get('cert_date_mmddyy')
        seq_no = data.get('seq_no', '00')
        dental_flag = data.get('dental_flag', False)

        if not claim_id:
            return jsonify({'status': 'error', 'message': 'claim_id is required'}), 400

        pythoncom.CoInitialize()
        
        try:
            sessions = attach_emulator_sessions(n=1)
            screen = sessions[0].Screen

            result = process_claim(
                screen=screen,
                claim_id=claim_id,
                method=method,
                cert_date_mmddyy=cert_date,
                seq_no=seq_no,
                dental_flag=dental_flag
            )

            return jsonify({'status': 'success', 'result': result}), 200

        finally:
            pythoncom.CoUninitialize()

    except Exception as e:
        logger.error(f"Error processing claim: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


if __name__ == '__main__':
    logger.info(f"Starting Windows Automation Service on {SERVICE_HOST}:{SERVICE_PORT}")
    logger.warning("⚠️  This service MUST run on Windows with EXTRA emulator open")
    app.run(host=SERVICE_HOST, port=SERVICE_PORT, debug=False, threaded=True)
