from rule_engine.functions.helpers import attach_emulator_sessions, process_claim
from rule_engine.registry import register_function

from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from typing import List, Dict, Any, Tuple
# from helpers import process_claim,attach_emulator_sessions
import pandas as pd

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

