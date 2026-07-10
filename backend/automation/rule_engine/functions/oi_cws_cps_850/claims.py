from rule_engine.functions.helpers import (
    attach_emulator_sessions, clean_name, get_screen_id, place_value,
    rtn_patient_seq_no, send_enter, send_pf, wait_for_screen,
)
from rule_engine.registry import register_function

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import List, Dict, Any, Tuple
# from helpers import process_claim,attach_emulator_sessions
import pandas as pd


def read_cps850_fields(screen) -> dict:
    out = {}
    out["EMPLOYEE"] = clean_name(screen.GetString(2, 7, 37).strip())
    out["SSN"] = screen.GetString(3, 72, 9).strip()
    out["CERT"] = screen.GetString(2, 72, 9).strip()
    out["MBR ID"] = screen.GetString(3, 50, 8).strip()
    out["MBR OPI"] = screen.GetString(2, 2, 4).strip()
    out["OPI2"] = screen.GetString(3, 2, 4).strip()
    out["CUSTOMER"] = screen.GetString(6, 50, 26).strip()
    out["PLAN #"] = screen.GetString(7, 50, 12).strip()
    out["EE EFF DT"] = screen.GetString(6, 16, 6).strip()
    out["EE TERM DT"] = screen.GetString(6, 29, 6).strip()
    out["EE CLASS"] = screen.GetString(6, 6, 3).strip()
    out["EE STATUS"] = screen.GetString(6, 13, 2).strip()
    out["DEP EFF DT"] = screen.GetString(7, 16, 6).strip()
    out["DEP TERM DT"] = screen.GetString(7, 29, 6).strip()
    out["DEP CLASS"] = screen.GetString(7, 6, 3).strip()
    out["WORK STATUS"] = screen.GetString(4, 51, 2).strip()
    out["PAID THRU DT"] = screen.GetString(8, 7, 6).strip()
    out["EE REPORTING"] = ""
    out["CSR NOTE"] = screen.GetString(9, 2, 58).strip() + "\n" + screen.GetString(10, 2, 58).strip()
    out["DATE OF BIRTH"] = screen.GetString(2, 55, 6).strip()
    out["EFFECTIVE DATE"] = screen.GetString(13, 40, 6).strip()
    out["REL"] = screen.GetString(13, 60, 2).strip()
    out["TERM DATE"] = screen.GetString(13, 50, 6).strip()
    out["CONTINUING COV"] = screen.GetString(6, 36, 1).strip()
    out["DATE"] = ""
    out["WAITING PERIOD"] = ""
    out["MARITAL STATUS"] = screen.GetString(2, 65, 1).strip()
    out["CLAIM PND IND"] = screen.GetString(13, 79, 2).strip()
    out["PRE-EX MET DT"] = ""
    out["FLEX ROLLOVER"] = ""
    out["PAY EMPLOYEE"] = ""
    out["ALTERNATE ADDRESS"] = ""
    out["PROIVDER NAME"] = screen.GetString(14, 6, 29).strip()
    out["BILLING NAME"] = screen.GetString(1, 39, 31).strip()
    out["TAX ID"] = screen.GetString(14, 40, 9).strip()
    out["OPI"] = screen.GetString(15, 59, 5).strip()
    out["ADDRESS"] = screen.GetString(3, 7, 38).strip() + "\n" + screen.GetString(4, 7, 38).strip()
    out["CITY"] = screen.GetString(5, 6, 20).strip()
    out["STATE"] = screen.GetString(5, 27, 2).strip()
    out["ZIP"] = screen.GetString(5, 30, 12).strip()
    out["EE DOB"] = screen.GetString(2, 55, 6).strip()
    out["LOCATION"] = screen.GetString(5, 50, 4).strip()
    out["EE TERM STAT"] = screen.GetString(6, 26, 2).strip()
    out["MBR ORG EFF DT"] = screen.GetString(6, 45, 4).strip()
    out["CONTINUING COVERAGE"] = screen.GetString(6, 36, 1).strip()
    out["DEP STATUS"] = screen.GetString(7, 13, 2).strip()
    out["POLICY EFF DT"] = screen.GetString(8, 53, 6).strip()
    out["DEP TERM STATUS"] = screen.GetString(7, 26, 2).strip()
    out[" TERM DATE"] = screen.GetString(8, 64, 7).strip()
    out["DEV COV STATUS"] = screen.GetString(7, 42, 7).strip()
    out["MENTAL VENDOR"] = screen.GetString(8, 77, 4).strip()
    out["FLEX"] = ""
    out["PRE-EX MOS"] = screen.GetString(7, 79, 2).strip()
    out["PRE-CERT"] = screen.GetString(4, 78, 3).strip()
    out["ROLLOVER"] = ""
    out["PRE-EXISTING"] = screen.GetString(6, 80, 1).strip()
    out["FAMILY COVERAGE"] = screen.GetString(12, 2, 3).strip()
    out["UPDATED"] = screen.GetString(12, 6, 6).strip()
    out["OTH INS TYPE"] = screen.GetString(11, 27, 2).strip()
    out["LAST UPDATE DATE"] = screen.GetString(11, 20, 6).strip()
    out["OTH INS EFF DT"] = screen.GetString(11, 30, 6).strip()
    out["OTH INS TERM DT"] = screen.GetString(11, 37, 6).strip()
    out["PROVIDER"] = screen.GetString(14, 6, 29).strip()
    out["BILLING NM"] = screen.GetString(1, 39, 31).strip()
    out[" ADDRESS"] = screen.GetString(15, 2, 25).strip()
    out[" CITY"] = screen.GetString(15, 28, 12).strip()
    out[" STATE"] = screen.GetString(15, 41, 2).strip()
    out[" ZIP"] = screen.GetString(15, 44, 10).strip()
    out["PHONE"] = screen.GetString(14, 59, 13).strip()
    out[" TAX ID"] = screen.GetString(14, 40, 9).strip()
    out["PCP"] = screen.GetString(20, 69, 12).strip()
    out[" OPI"] = screen.GetString(15, 59, 5).strip()
    out["SPECIALTY"] = screen.GetString(19, 70, 3).strip()
    out["TIER"] = screen.GetString(19, 79, 2).strip()
    out["RATE"] = screen.GetString(17, 70, 11).strip()
    out["FINANCIAL INVESTIGATION"] = screen.GetString(18, 70, 11).strip()
    out["TAXONOMY"] = ""
    out["PROVIDER NOTE"] = (
        screen.GetString(16, 2, 62).strip() + "\n" +
        screen.GetString(17, 2, 62).strip() + "\n" +
        screen.GetString(18, 2, 62).strip() + "\n" +
        screen.GetString(19, 2, 62).strip()
    )
    return out

def read_blx2460_fields(screen) -> dict:
    return {
        "UB/HCFA AFV FIELD": screen.GetString(23, 13, 1).strip(),
        "UB/HCFA CONDITION NOTE": screen.GetString(22, 44, 36).strip(),
        "UB TOB": screen.GetString(2, 54, 3).strip(),
    }

def read_cps450_fields(screen) -> dict:
    return {
        "UB/HCFA AFV FIELD": screen.GetString(3, 15, 1).strip(),
        "UB/HCFA CONDITION NOTE": screen.GetString(3, 46, 35).strip(),
        "UB TOB": screen.GetString(2, 54, 3).strip(),
        "HCFA AP CODE": screen.GetString(5, 68, 2).strip(),
        "HCFA CFV FIELD": screen.GetString(3, 17, 1).strip(),
    }

def read_cps310_fields(screen) -> dict:
    return {
        "PROVIDER ": screen.GetString(3, 2, 28).strip(),
        "ADDRESS ": screen.GetString(4, 2, 28).strip(),
        "CITY ": screen.GetString(6, 2, 23).strip(),
        "STATE ": screen.GetString(6, 26, 3).strip(),
        "ZIP ": screen.GetString(6, 30, 11).strip(),
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
        # PF9 entry
        send_pf(screen, 9)
        max_steps = 500
        steps = 0

        while steps < max_steps:
            steps += 1
            wait_for_screen(screen)
            sid = get_screen_id(screen).upper()

            if sid == "CPS520.01":
                # Claim entry
                if method.upper() == "SEARCH BY CCN":
                    place_value(screen, claim_id, 8, 15)
                elif method.upper() == "SEARCH BY CERT":
                    place_value(screen, claim_id, 9, 15)
                if cert_date_mmddyy:
                    place_value(screen, cert_date_mmddyy, 12, 15)
                if dental_flag:
                    place_value(screen, "D", 9, 59)
                send_enter(screen)

                # If still on CPS520.01, capture status and stop
                if get_screen_id(screen).upper() == "CPS520.01":
                    result["MACRO STATUS"] = (
                        screen.GetString(31, 2, 70).strip() + " " +
                        screen.GetString(30, 2, 70).strip()
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
                    screen.Putstring((seq_no or "00"), 2, 6)
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

        # PF9 end-of-claim and mark status done
        send_pf(screen, 9)
        result["MACRO STATUS"] = f"DONE.{result.get('MACRO STATUS', '')}"
        return result

    except Exception as e:
        print(e)
        # Return whatever we captured so far; MACRO STATUS may be empty if an early exception occurred
        return result


@register_function(
    name="convert_claims_data_to_csv", 
    inputs=[{"name": "output_path", "type": "string"}], # 
    outputs=[{"name": "status", "type": "boolean"}]
)
def convert_claims_data_to_csv(output_path,context=None) :
    """
    """
    print("Convert claims to csv")
    try:
        results = context.get("scrapped_claims")
        df = pd.DataFrame(results)
        df.to_csv(output_path)
        print("Successfully completed claims to DB\\CSV")
        return {"status":True}
    except Exception as e:
        return {"Status":False}
    

@register_function(
    name="scrap_claims_from_emulator", 
    inputs=[], # 
    outputs=[{"name": "scrapped_claims", "type": "list"}]
)
def scrap_claims_from_emulator(context=None) :
    """
    Processes claims in parallel using up to 4 emulator sessions, round-robin assignment,
    and returns results in the original input order.
    """
    print("Started scrap claims from emulator")
    claim_ids = context.get("claim_ids")
    if not claim_ids:
        return []

    try:
        sessions = attach_emulator_sessions(n=4)
    except Exception as e:
        # You can log or raise based on your preference
        print(f"Failed to attach sessions: {e}")
        # Fallback: process sequentially using your current code?
        # return _process_sequentially(claim_ids)
        raise

    worker_count = min(4, len(sessions))
    print(f"Using {worker_count} emulator session(s) for {len(claim_ids)} claim(s).")

    # Defaults you already use
    default_method = "SEARCH BY CCN"
    default_seq_no = "00"
    default_dental = False
    default_cert_mmddyy = None

    # Index claims so we can put results back in the same order
    indexed_claims: List[Tuple[int, str]] = list(enumerate(claim_ids))

    # Round-robin partition: bucket i gets i, i+worker_count, i+2*worker_count, ...
    buckets: List[List[Tuple[int, str]]] = [
        indexed_claims[i::worker_count] for i in range(worker_count)
    ]

    # We’ll collect results via a thread-safe queue as (idx, result_dict)
    out_q: Queue = Queue()

    def _worker(worker_idx: int, items: List[Tuple[int, str]]):
        """
        Runs on its own thread, using its own COM apartment.
        Each worker uses exactly one emulator session.
        """
        import pythoncom
        pythoncom.CoInitialize()
        try:
            session = sessions[worker_idx]
            screen = session.Screen
            try:
                screen.WaitHostQuiet(2000)
            except Exception:
                pass

            for (idx, cid) in items:
                try:
                    res = process_claim(
                        screen=screen,
                        claim_id=cid,
                        method=default_method,
                        cert_date_mmddyy=default_cert_mmddyy,
                        seq_no=default_seq_no,
                        dental_flag=default_dental,
                    )
                except Exception as e:
                    print(f"Worker {worker_idx} error on {cid}: {e}")
                    res = {
                        "CLAIM CONTROL #": cid,
                        "MACRO STATUS": f"ERROR: {e}",
                    }

                # Normalize None -> ""
                cleaned = {k: (v if v is not None else "") for k, v in res.items()}
                out_q.put((idx, cleaned))

        finally:
            # Keep it tidy
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    # Launch exactly one worker per session
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        for i in range(worker_count):
            pool.submit(_worker, i, buckets[i])

        # Reassemble results in original order
        results: List[Dict[str, Any]] = [None] * len(indexed_claims)
        collected = 0
        while collected < len(indexed_claims):
            idx, res = out_q.get()
            results[idx] = res
            collected += 1
    print(f"completed scrap claims from emulator {len(results)}")
    return {"scrapped_claims":results }

