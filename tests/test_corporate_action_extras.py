import unittest
import json
from typing import Dict, Any

from src.models.corporate_action_model import CorporateAction, ActionType, IssuerRef, SecurityRef
from src.core.ca_repository import _details_json


class CorporateActionExtrasSerializationTests(unittest.TestCase):
    def test_extras_is_serialized_into_details_json(self) -> None:
        ca = CorporateAction(
            action_type=ActionType.OTHER,
            issuer=IssuerRef(name="Test Co", cik="0001234567"),
            security=SecurityRef(ticker="TEST"),
            extras={
                "all_tickers": ["TEST", "TEST-B"],
                "extra_tickers": ["TEST-B"],
                "primary_ticker": "TEST",
            },
        )

        js = _details_json(ca)
        payload: Dict[str, Any] = json.loads(js)

        # Ensure extras exists and contains expected keys
        self.assertIn("extras", payload)
        self.assertEqual(payload["extras"].get("primary_ticker"), "TEST")
        self.assertListEqual(payload["extras"].get("all_tickers"), ["TEST", "TEST-B"])
        self.assertListEqual(payload["extras"].get("extra_tickers"), ["TEST-B"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
