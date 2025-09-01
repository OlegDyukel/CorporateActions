import unittest
from datetime import date

from src.processors.effective_date_resolver import (
    resolve_effective_date,
    format_estimate_for_display,
)


class EffectiveDateResolverTests(unittest.TestCase):
    def test_promotes_definitive_above_threshold(self) -> None:
        candidates = [
            {"kind": "estimated", "date": date(2025, 9, 29), "confidence": 0.8, "method": "llm_primary"},
            {"kind": "definitive", "date": date(2025, 9, 30), "confidence": 0.9, "method": "llm_followup"},
        ]
        promoted, extras = resolve_effective_date(candidates=candidates)

        self.assertEqual(promoted, date(2025, 9, 30))
        self.assertIn("effective_date_candidates", extras)
        self.assertIn("effective_date_recommendation", extras)
        rec = extras["effective_date_recommendation"]
        self.assertEqual(rec.get("kind"), "definitive")

    def test_no_promotion_below_threshold(self) -> None:
        candidates = [
            {"kind": "definitive", "date": date(2025, 9, 30), "confidence": 0.6, "method": "llm_primary"},
        ]
        promoted, extras = resolve_effective_date(candidates=candidates)
        self.assertIsNone(promoted)
        self.assertIn("effective_date_recommendation", extras)
        self.assertEqual(extras["effective_date_recommendation"]["kind"], "definitive")

    def test_window_estimate_formatting(self) -> None:
        candidates = [
            {
                "kind": "window",
                "start_date": date(2025, 10, 1),
                "end_date": date(2025, 12, 31),
                "qualifier": "Q4 2025",
                "confidence": 0.75,
                "method": "llm_primary",
            }
        ]
        promoted, extras = resolve_effective_date(candidates=candidates)
        self.assertIsNone(promoted)
        disp = format_estimate_for_display(extras)
        self.assertEqual(disp, "Q4 2025 (llm_primary, 0.75)")

    def test_relative_formatting(self) -> None:
        candidates = [
            {
                "kind": "relative",
                "qualifier": "within 60 days after shareholder approval",
                "confidence": 0.6,
                "method": "llm_followup",
            }
        ]
        _, extras = resolve_effective_date(candidates=candidates)
        disp = format_estimate_for_display(extras)
        self.assertEqual(disp, "within 60 days after shareholder approval (llm_followup, 0.60)")

    def test_ranking_definitive_beats_estimated_even_with_lower_conf(self) -> None:
        candidates = [
            {"kind": "estimated", "date": date(2025, 9, 29), "confidence": 0.95, "method": "llm_primary"},
            {"kind": "definitive", "date": date(2025, 9, 30), "confidence": 0.7, "method": "llm_followup"},
        ]
        _, extras = resolve_effective_date(candidates=candidates)
        rec = extras["effective_date_recommendation"]
        self.assertEqual(rec.get("kind"), "definitive")

    def test_no_candidates(self) -> None:
        promoted, extras = resolve_effective_date(candidates=[])
        self.assertIsNone(promoted)
        self.assertEqual(extras, {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
