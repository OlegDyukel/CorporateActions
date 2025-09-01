import unittest

from src.utils.metrics import Metrics


class MetricsTests(unittest.TestCase):
    def test_record_and_summary(self) -> None:
        m = Metrics()
        # 1: definitive without followup
        m.record(effective_date=True, had_estimate=True, promoted=False, followup_used=False)
        # 2: estimated only with followup
        m.record(effective_date=False, had_estimate=True, promoted=False, followup_used=True)
        # 3: promoted from estimate
        m.record(effective_date=True, had_estimate=True, promoted=True, followup_used=True)
        # 4: nothing
        m.record(effective_date=False, had_estimate=False, promoted=False, followup_used=False)

        s = m.summary()
        self.assertEqual(s["processed"], 4)
        self.assertEqual(s["definitive"], 2)
        self.assertEqual(s["estimated"], 1)  # one with estimate but no definitive
        self.assertEqual(s["promoted"], 1)
        self.assertEqual(s["followup_used"], 2)
        self.assertAlmostEqual(s["fill_rate"], 0.5)
        self.assertAlmostEqual(s["est_or_def_rate"], 0.75)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
