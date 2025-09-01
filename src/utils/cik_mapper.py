import requests
import json
import re
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple

@dataclass(frozen=True)
class SecurityRecord:
    """
    Represents a listed security for a registrant (CIK).

    Attributes:
        ticker: Exchange ticker symbol (e.g., 'TDS', 'TDS-PU').
        title: Registrant/company title from SEC dataset.
        exchange: Exchange name if available (e.g., 'NYSE', 'NASDAQ').
    """
    ticker: str
    title: str
    exchange: Optional[str] = None

class CIKMapper:
    """
    A utility to map CIKs to ticker symbols by fetching data from the SEC.
    """
    _CIK_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
    _CIK_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
    # Cache of CIK -> list of securities (ticker, title, exchange)
    _securities_by_cik: Optional[Dict[str, List[SecurityRecord]]] = None
    # Cache of (CIK, TICKER) -> exchange for precise lookup
    _exchange_by_cik_ticker: Optional[Dict[Tuple[str, str], str]] = None

    def __init__(self, user_agent: str):
        """
        Initializes the CIKMapper with the required User-Agent.

        Args:
            user_agent: The User-Agent string for SEC requests.
        """
        self.user_agent = user_agent

    def _initialize_map(self) -> None:
        """
        Downloads and processes SEC mapping files to build a per-CIK list of securities
        and a precise (CIK, TICKER) -> exchange map.
        """
        if self._securities_by_cik is not None and self._exchange_by_cik_ticker is not None:
            return

        print("Initializing CIK to Securities mapping...")
        securities_by_cik: Dict[str, Dict[str, SecurityRecord]] = {}
        exchange_by_cik_ticker: Dict[Tuple[str, str], str] = {}
        fallback_exchange_by_cik: Dict[str, str] = {}

        # 1) Load company_tickers.json -> base securities (no exchange info here)
        try:
            response = requests.get(self._CIK_TICKER_URL, headers={'User-Agent': self.user_agent})
            response.raise_for_status()
            data = response.json()
            for item in data.values():
                cik_key = str(item.get('cik_str'))
                ticker = str(item.get('ticker', '')).upper()
                title = str(item.get('title', '')).strip()
                if not cik_key or not ticker:
                    continue
                if cik_key not in securities_by_cik:
                    securities_by_cik[cik_key] = {}
                # De-dupe by ticker within CIK
                if ticker not in securities_by_cik[cik_key]:
                    securities_by_cik[cik_key][ticker] = SecurityRecord(ticker=ticker, title=title, exchange=None)
            print("CIK to Securities (base) mapping initialized successfully.")
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[CIK Mapper Error] Failed to download/parse tickers file: {e}")

        # 2) Load company_tickers_exchange.json -> exchange info; try to map per (cik, ticker)
        try:
            response = requests.get(self._CIK_EXCHANGE_URL, headers={'User-Agent': self.user_agent})
            response.raise_for_status()
            data = response.json()
            fields: List[str] = data.get('fields', [])
            rows: List[List[object]] = data.get('data', [])
            cik_index = fields.index('cik')
            exchange_index = fields.index('exchange')
            ticker_index = fields.index('ticker') if 'ticker' in fields else None

            for row in rows:
                cik_val = str(row[cik_index])
                cik_key = str(int(cik_val))  # normalize to non-padded
                exchange_val = str(row[exchange_index]).strip() if row[exchange_index] is not None else ''
                if ticker_index is not None:
                    ticker_val = str(row[ticker_index]).upper() if row[ticker_index] is not None else ''
                    if cik_key and ticker_val:
                        exchange_by_cik_ticker[(cik_key, ticker_val)] = exchange_val
                else:
                    # Fallback: only per-CIK exchange available
                    if cik_key:
                        fallback_exchange_by_cik[cik_key] = exchange_val
            print("CIK/Ticker to Exchange mapping initialized successfully.")
        except (requests.RequestException, json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"[CIK Mapper Error] Failed to initialize exchange map: {e}")

        # 3) Join exchange info into securities
        for cik_key, ticker_map in securities_by_cik.items():
            for tkr, sec in list(ticker_map.items()):
                exch = exchange_by_cik_ticker.get((cik_key, tkr)) or fallback_exchange_by_cik.get(cik_key)
                if exch:
                    ticker_map[tkr] = SecurityRecord(ticker=sec.ticker, title=sec.title, exchange=exch)

        # Freeze caches
        self._securities_by_cik = {cik: list(tmap.values()) for cik, tmap in securities_by_cik.items()}
        self._exchange_by_cik_ticker = exchange_by_cik_ticker
        print("CIK to Securities mapping ready (with exchanges where available).")

    def get_ticker_by_cik(self, cik: str) -> Optional[str]:
        """
        Retrieves the ticker symbol for a given CIK.

        Args:
            cik: The CIK string.

        Returns:
            The ticker symbol, or None if not found.
        """
        return self.get_primary_ticker_by_cik(cik)

    def get_all_tickers_by_cik(self, cik: str) -> List[str]:
        """Returns all known tickers for a given CIK (order not guaranteed)."""
        securities = self.get_securities_by_cik(cik)
        return [s.ticker for s in securities]

    def get_securities_by_cik(self, cik: str) -> List[SecurityRecord]:
        """Returns all known SecurityRecord entries for a given CIK."""
        if self._securities_by_cik is None:
            self._initialize_map()
        try:
            cik_key = str(int(cik))
        except ValueError:
            cik_key = cik
        return list(self._securities_by_cik.get(cik_key, [])) if self._securities_by_cik else []

    def get_exchange(self, cik: str, ticker: str) -> Optional[str]:
        """Returns the exchange for a given (CIK, ticker) if available."""
        if self._exchange_by_cik_ticker is None:
            self._initialize_map()
        try:
            cik_key = str(int(cik))
        except ValueError:
            cik_key = cik
        # Try precise map first
        if self._exchange_by_cik_ticker:
            exch = self._exchange_by_cik_ticker.get((cik_key, ticker.upper()))
            if exch:
                return exch
        # Fallback: infer from stored securities
        for sec in self.get_securities_by_cik(cik_key):
            if sec.ticker.upper() == ticker.upper() and sec.exchange:
                return sec.exchange
        return None

    # -------- Heuristics for primary ticker selection --------
    _PRIMARY_EXCH_HINTS = (
        "NASDAQ",
        "NYSE",
        "NYSE AMERICAN",
        "NYSEMKT",
        "NYSE ARCA",
    )

    _TITLE_DEPRIORITIZE = (
        "PREFERRED",
        "DEPOSITARY",
        "UNITS",
        "WARRANT",
        "NOTES",
        "BOND",
        "CONVERTIBLE",
    )

    _HEAVY_SUFFIX_PATTERNS = (
        re.compile(r"-P[A-Z]*$"),  # preferred series
        re.compile(r"-(WS|W)$"),   # warrants
        re.compile(r"-U$"),       # units
        re.compile(r"-R$"),       # rights
        re.compile(r"-N$"),       # notes/other series
    )

    _MILD_SUFFIX_PATTERNS = (
        re.compile(r"-(B|C)$"),   # class B/C common (dual-class)
        re.compile(r"\.[A-Z]$"), # dot-suffixed classes like BRK.A
    )

    def _is_primary_exchange(self, exchange: Optional[str]) -> bool:
        if not exchange:
            return False
        ex = exchange.upper()
        return any(hint in ex for hint in self._PRIMARY_EXCH_HINTS)

    def _title_penalty(self, title: str) -> int:
        t = title.upper()
        return 1 if any(k in t for k in self._TITLE_DEPRIORITIZE) else 0

    def _suffix_penalties(self, ticker: str) -> Tuple[int, int, int]:
        """
        Returns a tuple of penalties:
        (heavy_suffix_penalty, mild_suffix_penalty, has_symbol_penalty)
        """
        t = ticker.upper()
        heavy = 1 if any(p.search(t) for p in self._HEAVY_SUFFIX_PATTERNS) else 0
        mild = 1 if any(p.search(t) for p in self._MILD_SUFFIX_PATTERNS) else 0
        has_symbol = 1 if ("-" in t or "." in t) else 0
        return heavy, mild, has_symbol

    def get_primary_ticker_by_cik(self, cik: str) -> Optional[str]:
        """
        Selects a single primary ticker for the given CIK using heuristics:
        - Prefer titles without preferred/depositary/units/warrants/notes/bond/convertible.
        - Prefer tickers without heavy suffix patterns (-P*, -WS/-W, -U, -R, -N).
        - Prefer primary exchanges (NYSE/NASDAQ family) over OTC/unknown.
        - Deprioritize mild class suffixes (.-class, -B/-C), but allow if needed.
        - Break ties by shorter ticker, then alphabetical for determinism.
        """
        securities = self.get_securities_by_cik(cik)
        if not securities:
            return None

        def score(sec: SecurityRecord) -> Tuple[int, int, int, int, int, int, str]:
            title_pen = self._title_penalty(sec.title)
            heavy, mild, has_sym = self._suffix_penalties(sec.ticker)
            non_primary_exch = 0 if self._is_primary_exchange(sec.exchange) else 1
            # Lower tuple is better
            return (
                title_pen,
                heavy,
                non_primary_exch,
                mild,
                has_sym,
                len(sec.ticker),
                sec.ticker,
            )

        best = min(securities, key=score)
        return best.ticker if best else None

    def get_exchange_by_cik(self, cik: str) -> Optional[str]:
        """
        Retrieves the exchange for a given CIK.

        Args:
            cik: The CIK string.

        Returns:
            The exchange, or None if not found.
        """
        primary = self.get_primary_ticker_by_cik(cik)
        if not primary:
            return None
        return self.get_exchange(cik, primary)
