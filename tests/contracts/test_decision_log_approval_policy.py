"""Schema regression for pre-authorized pipeline approval decisions."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema


def test_decision_log_accepts_approval_policy_category():
    root = Path(__file__).resolve().parent.parent.parent
    schema = json.loads(
        (root / "schemas" / "artifacts" / "decision_log.schema.json").read_text(
            encoding="utf-8"
        )
    )
    artifact = {
        "version": "1.0",
        "project_id": "agnes-avatar-smoke",
        "decisions": [
            {
                "decision_id": "d-approval-1",
                "stage": "idea",
                "category": "approval_policy",
                "subject": "Pipeline approval scope",
                "options_considered": [
                    {
                        "option_id": "preauthorized",
                        "label": "Pre-authorized run",
                        "score": 1.0,
                        "reason": "The user explicitly approved the full smoke path",
                    }
                ],
                "selected": "preauthorized",
                "reason": "Preserve the user's explicit approval in the audit trail",
            }
        ],
    }

    jsonschema.validate(artifact, schema)
