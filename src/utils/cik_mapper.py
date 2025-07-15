import requests
import json
from typing import Dict, Optional

class CIKMapper:
    """
    A utility to map CIKs to ticker symbols by fetching data from the SEC.
    """
    _CIK_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
    _CIK_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
    _cik_to_ticker_map: Optional[Dict[str, str]] = None
    _cik_to_exchange_map: Optional[Dict[str, str]] = None

    def __init__(self, user_agent: str):
        """
        Initializes the CIKMapper with the required User-Agent.

        Args:
            user_agent: The User-Agent string for SEC requests.
        """
        self.user_agent = user_agent

    def _initialize_map(self) -> None:
        """Downloads and processes the CIK-to-ticker and CIK-to-exchange mapping files from the SEC."""
        if self._cik_to_ticker_map is None:
            print("Initializing CIK to Ticker mapping...")
            try:
                response = requests.get(self._CIK_TICKER_URL, headers={'User-Agent': self.user_agent})
                response.raise_for_status()
                data = response.json()
                self._cik_to_ticker_map = {str(item['cik_str']): item['ticker'] for item in data.values()}
                print("CIK to Ticker mapping initialized successfully.")
            except requests.exceptions.RequestException as e:
                print(f"Error downloading CIK to Ticker mapping: {e}")
            except json.JSONDecodeError as e:
                print(f"Error decoding CIK to Ticker JSON: {e}")

        if self._cik_to_exchange_map is None:
            print("Initializing CIK to Exchange mapping...")
            try:
                response = requests.get(self._CIK_EXCHANGE_URL, headers={'User-Agent': self.user_agent})
                response.raise_for_status()
                data = response.json()
                fields = data['fields']
                cik_index = fields.index('cik')
                exchange_index = fields.index('exchange')
                self._cik_to_exchange_map = {
                    str(row[cik_index]).zfill(10): row[exchange_index]
                    for row in data['data']
                }
                print("CIK to Exchange mapping initialized successfully.")
            except (requests.RequestException, json.JSONDecodeError, ValueError, KeyError) as e:
                print(f"[CIK Mapper Error] Failed to initialize CIK to Exchange map: {e}")
                self._cik_to_exchange_map = {}

    def get_ticker_by_cik(self, cik: str) -> Optional[str]:
        """
        Retrieves the ticker symbol for a given CIK.

        Args:
            cik: The CIK string.

        Returns:
            The ticker symbol, or None if not found.
        """
        if self._cik_to_ticker_map is None:
            self._initialize_map()
        # CIKs in the map are stored as integer strings, so we strip leading zeros.
        return self._cik_to_ticker_map.get(str(int(cik)))

    def get_exchange_by_cik(self, cik: str) -> Optional[str]:
        """
        Retrieves the exchange for a given CIK.

        Args:
            cik: The CIK string.

        Returns:
            The exchange, or None if not found.
        """
        if self._cik_to_exchange_map is None:
            self._initialize_map()
        # The exchange map uses a zero-padded 10-digit CIK as the key.
        return self._cik_to_exchange_map.get(cik.zfill(10))
