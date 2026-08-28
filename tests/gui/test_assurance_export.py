from __future__ import annotations

import unittest

from ourd.egcf.models import AssuranceCase
from ourd_gui.views.assurance import assurance_html, assurance_json, assurance_markdown


class AssuranceExportTests(unittest.TestCase):
    def fixture(self) -> AssuranceCase:
        return AssuranceCase(
            subject_id="task:1",
            top_claim="Candidate is safe <when scoped>",
            subclaims=[{"claim": "evidence covered", "status": True}],
            arguments=[],
            supporting_evidence=["evidence:1"],
            refuting_evidence=[],
            invariant_ids=[],
            decision_ids=[],
            capability_facts={"C3": "scoped"},
            approval_facts={"satisfied": True},
            rollback_argument={"covered": True},
            gaps=[],
            conflicts=[],
            uncertainties=["bounded"],
            conclusion="SUPPORTED",
            created_at="2026-08-21T00:00:00Z",
        )

    def test_exports_preserve_identity_and_escape_html(self) -> None:
        case = self.fixture()
        self.assertIn(case.object_id, assurance_json(case))
        self.assertIn(case.object_id, assurance_markdown(case))
        rendered = assurance_html(case)
        self.assertIn(case.object_id, rendered)
        self.assertIn("&lt;when scoped&gt;", rendered)
        self.assertNotIn("<when scoped>", rendered)


if __name__ == "__main__":
    unittest.main()

