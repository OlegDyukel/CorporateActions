import unittest
from unittest.mock import patch, MagicMock
import requests

from src.processors.filing_processor import fetch_filing_text


class FilingProcessorTests(unittest.TestCase):
    def test_fetch_filing_text_requires_user_agent(self) -> None:
        with self.assertRaises(ValueError):
            fetch_filing_text("edgar/data/0000000000/filing.txt", user_agent="")

    def test_fetch_filing_text_success(self) -> None:
        file_name = "edgar/data/0000000000/filing.txt"
        ua = "MyApp/1.0 my@email"

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.text = "OK"

        with patch("src.processors.filing_processor.requests.get", return_value=mock_response) as mock_get:
            text = fetch_filing_text(file_name, user_agent=ua)

        self.assertEqual(text, "OK")
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        called_headers = mock_get.call_args[1]["headers"]
        self.assertTrue(called_url.endswith(file_name))
        self.assertIn("User-Agent", called_headers)
        self.assertEqual(called_headers["User-Agent"], ua)

    def test_fetch_filing_text_failure_returns_empty_string(self) -> None:
        file_name = "edgar/data/0000000000/missing.txt"
        ua = "MyApp/1.0 my@email"

        with patch(
            "src.processors.filing_processor.requests.get",
            side_effect=requests.exceptions.RequestException("boom"),
        ):
            text = fetch_filing_text(file_name, user_agent=ua)

        self.assertEqual(text, "")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
