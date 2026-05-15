"""
Windows Automation Client
=========================

Client library for Linux/Docker systems to communicate with the Windows Automation Service.
This client abstracts away the HTTP calls to the Windows emulator service.

Usage:
    from windows_client import WindowsAutomationClient
    
    client = WindowsAutomationClient(host='192.168.1.100', port=5555)
    results = client.scrap_claims(['claim1', 'claim2', ...])
"""

import logging
import requests
from typing import List, Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class WindowsAutomationClientError(Exception):
    """Base exception for Windows Automation Client errors."""
    pass


class WindowsServiceUnavailable(WindowsAutomationClientError):
    """Raised when Windows service is unreachable."""
    pass


class WindowsAutomationClient:
    """
    Client for communicating with Windows Automation Service.
    
    Attributes:
        base_url: Base URL of the Windows service (e.g., http://localhost:5555)
        timeout: Request timeout in seconds
        max_retries: Number of retry attempts
    """

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 5555,
        timeout: int = 300,
        max_retries: int = 3
    ):
        """
        Initialize the Windows Automation Client.
        
        Args:
            host: Hostname/IP of Windows service
            port: Port of Windows service
            timeout: Request timeout in seconds (default 300 for long-running operations)
            max_retries: Number of retry attempts
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        
        # Create session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Windows service.
        
        Args:
            method: HTTP method ('GET', 'POST', etc.)
            endpoint: API endpoint path
            **kwargs: Additional arguments for requests
            
        Returns:
            Response JSON
            
        Raises:
            WindowsServiceUnavailable: If service is unreachable
            WindowsAutomationClientError: For other errors
        """
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault('timeout', self.timeout)

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError as e:
            msg = f"Cannot connect to Windows service at {self.base_url}"
            logger.error(msg)
            raise WindowsServiceUnavailable(msg) from e

        except requests.exceptions.Timeout:
            msg = f"Windows service request timeout after {self.timeout}s"
            logger.error(msg)
            raise WindowsServiceUnavailable(msg)

        except requests.exceptions.HTTPError as e:
            msg = f"Windows service returned error: {response.status_code} - {response.text}"
            logger.error(msg)
            raise WindowsAutomationClientError(msg) from e

        except Exception as e:
            msg = f"Error communicating with Windows service: {str(e)}"
            logger.error(msg)
            raise WindowsAutomationClientError(msg) from e

    def health_check(self) -> bool:
        """
        Check if Windows service is available.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            response = self._make_request('GET', '/health')
            return response.get('status') == 'healthy'
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def scrap_claims(
        self,
        claim_ids: List[str],
        method: str = 'SEARCH BY CCN',
        cert_date_mmddyy: Optional[str] = None,
        seq_no: str = '00',
        dental_flag: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Scrap multiple claims from emulator.
        
        Args:
            claim_ids: List of claim IDs to scrap
            method: Search method ('SEARCH BY CCN' or 'SEARCH BY CERT')
            cert_date_mmddyy: Certificate date in MMDDYY format
            seq_no: Sequence number
            dental_flag: Whether to process as dental claim
            
        Returns:
            List of claim result dictionaries
            
        Raises:
            WindowsServiceUnavailable: If service is unavailable
            WindowsAutomationClientError: For processing errors
        """
        if not claim_ids:
            logger.warning("No claim IDs provided")
            return []

        logger.info(f"Requesting to scrap {len(claim_ids)} claims from Windows service")

        payload = {
            'claim_ids': claim_ids,
            'method': method,
            'cert_date_mmddyy': cert_date_mmddyy,
            'seq_no': seq_no,
            'dental_flag': dental_flag
        }

        try:
            response = self._make_request(
                'POST',
                '/scrap-claims',
                json=payload
            )

            if response.get('status') != 'success':
                raise WindowsAutomationClientError(
                    f"Service returned error: {response.get('message', 'Unknown error')}"
                )

            results = response.get('results', [])
            logger.info(f"Successfully scraped {len(results)} claims")
            return results

        except WindowsServiceUnavailable:
            raise
        except Exception as e:
            logger.error(f"Error scraping claims: {e}")
            raise

    def process_claim(
        self,
        claim_id: str,
        method: str = 'SEARCH BY CCN',
        cert_date_mmddyy: Optional[str] = None,
        seq_no: str = '00',
        dental_flag: bool = False
    ) -> Dict[str, Any]:
        """
        Process a single claim from emulator.
        
        Args:
            claim_id: Claim ID to process
            method: Search method
            cert_date_mmddyy: Certificate date in MMDDYY format
            seq_no: Sequence number
            dental_flag: Whether to process as dental claim
            
        Returns:
            Claim result dictionary
            
        Raises:
            WindowsServiceUnavailable: If service is unavailable
            WindowsAutomationClientError: For processing errors
        """
        logger.info(f"Processing claim {claim_id} via Windows service")

        payload = {
            'claim_id': claim_id,
            'method': method,
            'cert_date_mmddyy': cert_date_mmddyy,
            'seq_no': seq_no,
            'dental_flag': dental_flag
        }

        try:
            response = self._make_request(
                'POST',
                '/process-claim',
                json=payload
            )

            if response.get('status') != 'success':
                raise WindowsAutomationClientError(
                    f"Service returned error: {response.get('message', 'Unknown error')}"
                )

            return response.get('result', {})

        except WindowsServiceUnavailable:
            raise
        except Exception as e:
            logger.error(f"Error processing claim: {e}")
            raise


# Convenience functions for direct usage

def get_windows_client() -> WindowsAutomationClient:
    """
    Get a configured Windows Automation Client using environment variables.
    
    Environment variables:
        WINDOWS_SERVICE_HOST: Host/IP of Windows service (default: localhost)
        WINDOWS_SERVICE_PORT: Port of Windows service (default: 5555)
        WINDOWS_SERVICE_TIMEOUT: Request timeout in seconds (default: 300)
    
    Returns:
        Configured WindowsAutomationClient instance
    """
    import os
    
    host = os.getenv('WINDOWS_SERVICE_HOST', 'localhost')
    port = int(os.getenv('WINDOWS_SERVICE_PORT', 5555))
    timeout = int(os.getenv('WINDOWS_SERVICE_TIMEOUT', 300))
    
    return WindowsAutomationClient(host=host, port=port, timeout=timeout)
