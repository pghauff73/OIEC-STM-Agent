from __future__ import annotations

import unittest

from ourd_gui.redaction import MAX_DEPTH_MARKER, REDACTED, safe_projection


class RedactionTests(unittest.TestCase):
    def test_secret_like_fields_are_redacted_without_hiding_usage_counts(self) -> None:
        projected = safe_projection(
            {
                "api_key": "sensitive",
                "nested": {"access_token": "sensitive", "tokens": 42},
            }
        )
        self.assertEqual(REDACTED, projected["api_key"])
        self.assertEqual(REDACTED, projected["nested"]["access_token"])
        self.assertEqual(42, projected["nested"]["tokens"])

    def test_deep_and_large_values_are_bounded(self) -> None:
        nested = {"level": {"level": {"level": {"value": 1}}}}
        projected = safe_projection(nested, max_depth=3, max_items=2)
        self.assertEqual(MAX_DEPTH_MARKER, projected["level"]["level"]["level"])
        items = safe_projection([1, 2, 3], max_items=2)
        self.assertEqual(3, len(items))


if __name__ == "__main__":
    unittest.main()
