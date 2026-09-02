from __future__ import annotations

import unittest

from ourd.interaction import InterpretedIntent


class InterpretedIntentTests(unittest.TestCase):
    def test_signature_is_order_independent_for_set_like_fields(self) -> None:
        first = InterpretedIntent(
            source_text="inspect files",
            objective="inspect files",
            mode="inspect",
            target_paths=("b.py", "a.py", "a.py"),
            constraints=("safe", "bounded"),
            requested_outputs=("evidence", "inspection"),
        )
        second = InterpretedIntent(
            source_text="inspect files",
            objective="inspect files",
            mode="INSPECT",
            target_paths=("a.py", "b.py"),
            constraints=("bounded", "safe"),
            requested_outputs=("inspection", "evidence"),
        )
        self.assertEqual(first.intent_id, second.intent_id)
        self.assertEqual(first.signature, second.signature)

    def test_signature_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "signature mismatch"):
            InterpretedIntent(
                source_text="inspect parser",
                objective="inspect parser",
                signature="not-the-signature",
            )

    def test_authoritative_intent_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot be authoritative"):
            InterpretedIntent(
                source_text="inspect parser",
                objective="inspect parser",
                authoritative=True,
            )

    def test_mutating_mode_forces_risk_floor_and_confirmation(self) -> None:
        intent = InterpretedIntent(
            source_text="write parser",
            objective="write parser",
            mode="WRITE",
            proposed_risk="L0",
        )
        self.assertEqual("L1", intent.proposed_risk)
        self.assertTrue(intent.requires_confirmation)


if __name__ == "__main__":
    unittest.main()
