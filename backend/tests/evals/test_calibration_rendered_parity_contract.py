from __future__ import annotations

import json

from scripts.evals.calibration_rendered_parity_contract import FIXTURE, evaluate


def cases() -> list[dict]:
    return json.loads(FIXTURE.read_text())["cases"]


def test_committed_contract_cases() -> None:
    for case in cases():
        assert evaluate(case["input"]) == case["expected"], case["id"]


def test_current_fixture_only_gate_cannot_mark_exam_green() -> None:
    current = next(case for case in cases() if case["id"] == "current-cal-p026-source-and-fixture-check")
    assert evaluate(current["input"])["verdict"] == "REFUSE"


def test_every_figure_mutation_bites() -> None:
    clean = next(case for case in cases() if case["id"] == "real-one-payload-parity-shape")["input"]
    for field in clean["native"]["figures"]:
        mutated = json.loads(json.dumps(clean))
        value = mutated["native"]["figures"][field]
        mutated["native"]["figures"][field] = not value if isinstance(value, bool) else f"mutated-{value}"
        assert evaluate(mutated)["verdict"] == "REFUSE", field
