"""
Claims Functions for Rule Engine
=================================

These functions are registered with the rule engine and can be called
from within rule workflows. 

Functions that interact with the EXTRA emulator communicate with
the Windows Automation Service, which must be running on Windows.
"""

from rule_engine.registry import register_function
from windows_client import get_windows_client, WindowsAutomationClientError, WindowsServiceUnavailable

from typing import List, Dict, Any
import pandas as pd
import logging

logger = logging.getLogger(__name__)


@register_function(
    name="convert_claims_data_to_csv", 
    inputs=[{"name": "output_path", "type": "string"}], 
    outputs=[{"name": "status", "type": "boolean"}]
)
def convert_claims_data_to_csv(output_path, context=None):
    """Convert scrapped claims data to CSV file."""
    logger.info(f"Converting claims to CSV: {output_path}")
    try:
        results = context.get("scrapped_claims")
        if not results:
            logger.warning("No scrapped claims in context")
            return {"status": False}
        df = pd.DataFrame(results)
        df.to_csv(output_path, index=False)
        logger.info(f"Successfully saved {len(results)} claims to CSV")
        return {"status": True}
    except Exception as e:
        logger.error(f"Error converting claims to CSV: {e}")
        return {"status": False}


@register_function(
    name="scrap_claims_from_emulator", 
    inputs=[],
    outputs=[{"name": "scrapped_claims", "type": "list"}]
)
def scrap_claims_from_emulator(context=None):
    """
    Scrap claims from EXTRA emulator via Windows Automation Service.
    
    This function communicates with a Windows-based automation service that
    handles all emulator interactions. Requires windows_automation_service.py
    running on Windows with EXTRA emulator open.
    """
    logger.info("Starting scrap claims from emulator")
    
    claim_ids = context.get("claim_ids", [])
    if not claim_ids:
        logger.warning("No claim IDs provided in context")
        return {"scrapped_claims": []}

    try:
        client = get_windows_client()
        
        if not client.health_check():
            raise WindowsServiceUnavailable(
                f"Windows service unavailable at {client.base_url}. "
                "Make sure windows_automation_service.py is running on Windows."
            )
        
        logger.info(f"Requesting to scrap {len(claim_ids)} claims from Windows service")
        
        results = client.scrap_claims(
            claim_ids=claim_ids,
            method=context.get("method", "SEARCH BY CCN"),
            cert_date_mmddyy=context.get("cert_date_mmddyy"),
            seq_no=context.get("seq_no", "00"),
            dental_flag=context.get("dental_flag", False)
        )
        
        cleaned_results = [
            {k: (v if v is not None else "") for k, v in result.items()}
            for result in results
        ]
        
        logger.info(f"Successfully scrapped {len(cleaned_results)} claims")
        return {"scrapped_claims": cleaned_results}
        
    except WindowsServiceUnavailable as e:
        logger.error(f"Windows service error: {e}")
        raise Exception(f"Cannot access Windows Automation Service. {str(e)}") from e
    except WindowsAutomationClientError as e:
        logger.error(f"Error from Windows service: {e}")
        raise Exception(f"Windows service error: {str(e)}") from e
    except Exception as e:
        logger.error(f"Unexpected error scraping claims: {e}")
        raise
