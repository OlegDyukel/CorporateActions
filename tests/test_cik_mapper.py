import unittest
from unittest.mock import patch, Mock

from src.utils.cik_mapper import CIKMapper


class CIKMapperHeuristicsTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset class-level caches to avoid cross-test contamination
        CIKMapper._securities_by_cik = None
        CIKMapper._exchange_by_cik_ticker = None

    def _mock_get(self, url_returns):
        """Helper to create a requests.get mock with per-URL JSON bodies."""
        def _side_effect(url, headers=None):
            body = url_returns.get(url)
            if body is None:
                raise AssertionError(f"Unexpected URL requested: {url}")
            m = Mock()
            m.raise_for_status = Mock()
            m.json = Mock(return_value=body)
            return m
        return _side_effect

    @patch("src.utils.cik_mapper.requests.get")
    def test_primary_ticker_prefers_common_over_pref_warrant_and_primary_exchange(self, mock_get):
        # Arrange mock SEC payloads
        tickers_json = {
            "0": {"cik_str": 1234567, "ticker": "ABC", "title": "ABC Inc. Common Stock"},
            "1": {"cik_str": 1234567, "ticker": "ABC-PB", "title": "ABC Inc. Preferred Series B"},
            "2": {"cik_str": 1234567, "ticker": "ABC-WS", "title": "ABC Inc. Warrants"},
        }
        exchange_json = {
            "fields": ["cik", "entityName", "ticker", "exchange"],
            "data": [
                [1234567, "ABC Inc.", "ABC", "NASDAQ"],
                [1234567, "ABC Inc.", "ABC-PB", "NYSE"],
                [1234567, "ABC Inc.", "ABC-WS", "NYSE"],
            ],
        }
        url_map = {
            CIKMapper._CIK_TICKER_URL: tickers_json,
            CIKMapper._CIK_EXCHANGE_URL: exchange_json,
        }
        mock_get.side_effect = self._mock_get(url_map)

        mapper = CIKMapper(user_agent="test-UA")

        # Act
        primary = mapper.get_primary_ticker_by_cik("0001234567")
        all_tickers = set(mapper.get_all_tickers_by_cik("0001234567"))
        exch_primary = mapper.get_exchange("0001234567", "ABC")
        exch_pref = mapper.get_exchange("0001234567", "ABC-PB")

        # Assert
        self.assertEqual(primary, "ABC")
        self.assertSetEqual(all_tickers, {"ABC", "ABC-PB", "ABC-WS"})
        self.assertEqual(exch_primary, "NASDAQ")
        self.assertEqual(exch_pref, "NYSE")

    @patch("src.utils.cik_mapper.requests.get")
    def test_dual_class_mild_suffix_deprioritized(self, mock_get):
        # Arrange mock SEC payloads
        tickers_json = {
            "0": {"cik_str": 7654321, "ticker": "XYZ", "title": "XYZ Corp. Class A Common"},
            "1": {"cik_str": 7654321, "ticker": "XYZ-B", "title": "XYZ Corp. Class B Common"},
        }
        exchange_json = {
            "fields": ["cik", "entityName", "ticker", "exchange"],
            "data": [
                [7654321, "XYZ Corp.", "XYZ", "NASDAQ"],
                [7654321, "XYZ Corp.", "XYZ-B", "NASDAQ"],
            ],
        }
        url_map = {
            CIKMapper._CIK_TICKER_URL: tickers_json,
            CIKMapper._CIK_EXCHANGE_URL: exchange_json,
        }
        mock_get.side_effect = self._mock_get(url_map)

        mapper = CIKMapper(user_agent="test-UA")

        # Act
        primary = mapper.get_primary_ticker_by_cik("7654321")
        all_tickers = set(mapper.get_all_tickers_by_cik("7654321"))

        # Assert
        self.assertEqual(primary, "XYZ")
        self.assertSetEqual(all_tickers, {"XYZ", "XYZ-B"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
