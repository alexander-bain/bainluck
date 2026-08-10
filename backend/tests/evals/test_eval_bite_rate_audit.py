from __future__ import annotations

import json

from scripts.evals.eval_bite_rate_audit import FIXTURE, evaluate_sample, validate_retro


def payload() -> dict:
    return json.loads(FIXTURE.read_text())


def test_frozen_40_case_sample_mutations_all_bite() -> None:
    result = evaluate_sample(payload())
    assert result["total"] == 40
    assert result["mutation_bites"] == 40, [row for row in result["rows"] if not row["bites"]]
    assert result["mutation_bite_rate"] == 1.0


def test_mock_shape_rate_is_reported_separately_and_strictly() -> None:
    result = evaluate_sample(payload())
    assert result["real_boundaries"] == 0
    assert result["real_boundary_rate"] == 0.0
    assert {row["boundary"] for row in result["rows"]} == {"dict_standin"}


def test_weekly_retro_names_production_evidence_and_catcher() -> None:
    assert validate_retro(payload()) == []
    assert len(payload()["escaped_defect_retro"]) == 6
