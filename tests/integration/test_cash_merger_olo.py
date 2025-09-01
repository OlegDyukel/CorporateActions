import os
import unittest
from datetime import date
from decimal import Decimal

from pathlib import Path
from dotenv import load_dotenv

from src.models.corporate_action_model import (
    CorporateAction,
    ActionType,
    IssuerRef,
    SecurityRef,
)
from src.processors.html_parser import parse_html_to_text
from src.processors.llm_extractor import llm_extract, apply_llm_to_corporate_action


OLO_8K_URL = "https://www.sec.gov/Archives/edgar/data/1431695/000114036125024753/ef20051581_8k.htm"

# Load .env from project root so OPENAI_API_KEY, EDGAR_* are available during tests
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _truthy_env(name: str, default: str = "") -> bool:
    val = os.getenv(name, default).strip().lower()
    return val in {"1", "true", "yes", "on"}


@unittest.skipUnless(
    _truthy_env("RUN_INTEGRATION_TESTS"),
    "Set RUN_INTEGRATION_TESTS=true to run network/LLM integration tests.",
)
class TestOloCashMergerIntegration(unittest.TestCase):
    def _user_agent(self) -> str:
        identity = os.getenv("EDGAR_IDENTITY")
        email = os.getenv("EDGAR_EMAIL")
        if not identity or not email:
            self.skipTest("EDGAR_IDENTITY/EDGAR_EMAIL are required for SEC requests.")
        return f"{identity} {email}"

    def _ensure_openai(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            self.skipTest("OPENAI_API_KEY is required for LLM extraction.")

    def test_extract_cash_merger_terms(self) -> None:
        self._ensure_openai()
        ua = self._user_agent()

        # 1) Fetch and parse the HTML into clean text
        text = parse_html_to_text(OLO_8K_URL, user_agent=ua)
        self.assertIsNotNone(text)
        self.assertIn("olo", text.lower())

        # 2) Run LLM extraction on the parsed text
        res = llm_extract(text or "", company="Olo Inc")
        if res is None:
            self.skipTest("LLM extraction unavailable or disabled (OpenAI SDK/LLM_ENABLED/API/connectivity).")

        # 3) Validate key extracted elements
        # Expect a cash merger with $10.25 per share
        self.assertEqual((res.action_type or "").lower(), ActionType.MERGER_CASH)
        self.assertIsNotNone(res.cash_per_share)
        self.assertEqual((res.cash_per_share.currency or "").upper(), "USD")
        self.assertEqual(Decimal(res.cash_per_share.amount), Decimal("10.25"))

        # Announcement date is known; assert if present
        if res.announce_date is not None:
            self.assertEqual(res.announce_date, date(2025, 7, 3))

        # 4) Apply to a base CorporateAction and ensure validators are satisfied
        base = CorporateAction(
            action_type=ActionType.OTHER,
            issuer=IssuerRef(name="Olo Inc"),
            security=SecurityRef(ticker="OLO", exchange_mic="XNYS"),
        )
        updated = apply_llm_to_corporate_action(base, res)
        self.assertEqual(updated.action_type, ActionType.MERGER_CASH)
        self.assertIsNotNone(updated.terms.cash_per_share)
        self.assertEqual(updated.terms.cash_per_share.currency, "USD")
        self.assertEqual(updated.terms.cash_per_share.amount, Decimal("10.25"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
