from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional
import threading

import pandas as pd


class ExchangeResolver:
    """Loads exchange alias/MIC mappings from a CSV and provides lookup helpers.

    CSV format (src/config/exchanges.csv):
    - alias: human-entered exchange string (e.g., 'NASDAQ', 'NYSE ARCA')
    - mic: ISO 10383 MIC code (e.g., 'XNAS', 'ARCX')
    - display_name: human-friendly display name (e.g., 'NASDAQ', 'NYSE ARCA')
    """

    def __init__(self, csv_path: Path) -> None:
        self._csv_path = csv_path
        self._alias_to_mic: Dict[str, str] = {}
        self._mic_to_name: Dict[str, str] = {}
        self._loaded: bool = False
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load()
            self._loaded = True

    def _load(self) -> None:
        self._alias_to_mic.clear()
        self._mic_to_name.clear()
        try:
            df = pd.read_csv(self._csv_path, dtype=str).fillna("")
        except Exception:
            # Missing or unreadable file: leave maps empty; lookups will fall back gracefully
            return

        for _, row in df.iterrows():
            alias = str(row.get("alias", "")).strip().upper()
            mic = str(row.get("mic", "")).strip().upper()
            display = str(row.get("display_name", "")).strip()
            if alias and mic:
                self._alias_to_mic[alias] = mic
            if mic and display and mic not in self._mic_to_name:
                self._mic_to_name[mic] = display

    def to_mic(self, exchange_name: Optional[str]) -> Optional[str]:
        if not exchange_name:
            return None
        self._ensure_loaded()
        key = exchange_name.strip().upper()
        return self._alias_to_mic.get(key)

    def mic_to_name(self, mic: Optional[str]) -> Optional[str]:
        if not mic:
            return None
        self._ensure_loaded()
        key = mic.strip().upper()
        # If not found, return the MIC itself so callers see something reasonable
        return self._mic_to_name.get(key, key)


# Module-level singleton
_RESOLVER: Optional[ExchangeResolver] = None


def get_exchange_resolver() -> ExchangeResolver:
    global _RESOLVER
    if _RESOLVER is None:
        # Compute default path: src/utils -> src/config/exchanges.csv
        base_src = Path(__file__).resolve().parents[1]
        csv_path = base_src / "config" / "exchanges.csv"
        _RESOLVER = ExchangeResolver(csv_path)
    return _RESOLVER
