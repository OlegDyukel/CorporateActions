import unittest
from decimal import Decimal
from datetime import date

from src.models.corporate_action_model import CorporateAction, ActionType
from src.processors.llm_extractor import (
    LLMExtractionResult,
    LLMMonetary,
    apply_llm_to_corporate_action,
)


class LLMExtractorApplyTests(unittest.TestCase):
    def test_apply_llm_sets_ratio_and_action_type_forward_split(self) -> None:
        base = CorporateAction(action_type=ActionType.OTHER)
        res = LLMExtractionResult(action_type=ActionType.FORWARD_SPLIT, ratio="2-for-1")

        updated = apply_llm_to_corporate_action(base, res)

        self.assertEqual(updated.action_type, ActionType.FORWARD_SPLIT)
        self.assertIsNotNone(updated.terms.ratio)
        self.assertEqual(str(updated.terms.ratio), "2-for-1")
        self.assertEqual(updated.terms.ratio.as_decimal(), Decimal("2"))

    def test_apply_llm_sets_cash_dividend(self) -> None:
        base = CorporateAction(action_type=ActionType.OTHER)
        res = LLMExtractionResult(
            action_type=ActionType.CASH_DIVIDEND,
            cash_per_share=LLMMonetary(currency="USD", amount=Decimal("0.25")),
        )

        updated = apply_llm_to_corporate_action(base, res)

        self.assertEqual(updated.action_type, ActionType.CASH_DIVIDEND)
        self.assertIsNotNone(updated.terms.cash_per_share)
        self.assertEqual(updated.terms.cash_per_share.currency, "USD")
        self.assertEqual(updated.terms.cash_per_share.amount, Decimal("0.25"))

    def test_apply_llm_does_not_set_effective_date_from_estimates(self) -> None:
        base = CorporateAction(action_type=ActionType.OTHER)
        res = LLMExtractionResult(
            effective_date=None,
            effective_date_estimates=[
                {
                    "kind": "relative",
                    "qualifier": "within 60 days after shareholder approval",
                    "confidence": 0.7,
                }
            ],
        )

        updated = apply_llm_to_corporate_action(base, res)

        self.assertIsNone(updated.effective_date)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
