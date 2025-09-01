import unittest
from unittest.mock import patch, Mock

from src.sources import sec_submissions as ss


class SECSubmissionsTests(unittest.TestCase):
    @patch("requests.get")
    def test_get_company_submissions_uses_padded_cik(self, mock_get):
        mock_resp = Mock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"ok": True}
        mock_get.return_value = mock_resp

        cik = "320193"  # Apple
        user_agent = "test-agent"
        res = ss.get_company_submissions(cik, user_agent)

        self.assertEqual(res, {"ok": True})
        self.assertTrue(mock_get.called)
        called_url = mock_get.call_args[0][0]
        self.assertIn("CIK0000320193.json", called_url)
        headers = mock_get.call_args[1]["headers"]
        self.assertEqual(headers["User-Agent"], user_agent)

    @patch("src.sources.sec_submissions.get_company_submissions")
    def test_get_recent_company_filings_filters_and_builds_urls(self, mock_submissions):
        mock_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-K"],
                    "accessionNumber": ["0000320193-25-000001", "0000320193-25-000002"],
                    "filingDate": ["2025-08-20", "2025-08-19"],
                    "primaryDocument": ["a8k.htm", "a10k.htm"],
                }
            }
        }
        cik = "0000320193"
        items = ss.get_recent_company_filings(cik, user_agent="ua", limit=5, form_filter=["8-K"]) 

        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["form"], "8-K")
        self.assertEqual(it["accessionNumber"], "0000320193-25-000001")
        # CIK numeric segment should be without leading zeros
        self.assertIn("/edgar/data/320193/", it["html_url"])  # CIK numeric dir
        self.assertTrue(it["html_url"].endswith("/a8k.htm"))
        self.assertTrue(it["txt_url"].endswith("0000320193-25-000001.txt"))

    @patch("src.sources.sec_submissions.get_company_submissions")
    def test_get_recent_company_filings_respects_limit(self, mock_submissions):
        mock_submissions.return_value = {
            "filings": {
                "recent": {
                    "form": ["8-K", "8-K", "8-K"],
                    "accessionNumber": [
                        "0000320193-25-000001",
                        "0000320193-25-000002",
                        "0000320193-25-000003",
                    ],
                    "filingDate": ["2025-08-20", "2025-08-19", "2025-08-18"],
                    "primaryDocument": ["a1.htm", "a2.htm", "a3.htm"],
                }
            }
        }
        items = ss.get_recent_company_filings("0000320193", user_agent="ua", limit=2, form_filter=["8-K"]) 
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["html_url"].endswith("/a1.htm"))
        self.assertTrue(items[1]["html_url"].endswith("/a2.htm"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
