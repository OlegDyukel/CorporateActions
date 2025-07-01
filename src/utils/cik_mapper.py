import requests
import json
from typing import Dict, Optional

class CIKMapper:
    """
    A utility to map CIKs to ticker symbols by fetching data from the SEC.
    """
    _CIK_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
    _cik_to_ticker_map: Optional[Dict[str, str]] = None

    def __init__(self, user_agent: str):
        """
        Initializes the CIKMapper with the required User-Agent.

        Args:
            user_agent: The User-Agent string for SEC requests.
        """
        self.user_agent = user_agent

    def _initialize_map(self) -> None:
        """Downloads and processes the CIK-to-ticker mapping file from the SEC."""
        print("Initializing CIK to Ticker mapping...")
        try:
            response = requests.get(self._CIK_TICKER_URL, headers={'User-Agent': self.user_agent})
            response.raise_for_status()
            data = response.json()

            # The JSON is a dictionary where keys are indices and values are company data
            self._cik_to_ticker_map = {
                str(item['cik_str']).zfill(10): item['ticker']
                for item in data.values()
            }
            print("CIK to Ticker mapping initialized successfully.")
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[CIK Mapper Error] Failed to initialize CIK map: {e}")
            self._cik_to_ticker_map = {}

    def get_ticker(self, cik: str) -> str:
        """
        Retrieves the ticker symbol for a given CIK.

        Args:
            cik: The 10-digit CIK string.

        Returns:
            The ticker symbol, or 'N/A' if not found.
        """
        if self._cik_to_ticker_map is None:
            self._initialize_map()
        
        # Ensure the map was initialized successfully
        if self._cik_to_ticker_map is None:
             return 'N/A'

        return self._cik_to_ticker_map.get(cik, 'N/A')
