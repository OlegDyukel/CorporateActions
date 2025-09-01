import unittest
from typing import List

from src.processors.filing_parser import extract_8k_items


class Extract8KItemsTests(unittest.TestCase):
    def test_basic_patterns_and_case(self) -> None:
        text = (
            "This is an 8-K. ITEM 1.01. Entry into a Material Agreement.\n"
            "Later, Items 5.02 (Director changes). Also item 9.01 exhibits."
        )
        items: List[str] = extract_8k_items(text)
        self.assertListEqual(items, ["1.01", "5.02", "9.01"])  # preserves order

    def test_deduplicates_preserving_order(self) -> None:
        text = (
            "Item 1.01 Agreement... more text ... Item 1.01 Additional disclosure.\n"
            "Item 2.01 Completion of Acquisition."
        )
        items = extract_8k_items(text)
        self.assertListEqual(items, ["1.01", "2.01"])  # de-duplicated

    def test_no_items_returns_empty(self) -> None:
        text = "This filing does not contain any item sections."
        self.assertListEqual(extract_8k_items(text), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
