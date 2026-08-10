from __future__ import annotations

import json

from scripts.evals.native_surface_authority_contract import FIXTURE, evaluate, evaluate_corpus


def corpus() -> dict:
    return json.loads(FIXTURE.read_text())


def test_corpus_matches_oracle() -> None:
    result = evaluate_corpus(corpus())
    assert result["total"] == 12
    assert result["passed"] == 12, result["cases"]


def test_every_native_guard_bites() -> None:
    reasons = {reason for case in corpus()["cases"] for reason in evaluate(case["input"])}
    assert reasons == {
        "ANALYTICS_WITHOUT_CONSENT",
        "MISSING_SCORE_RENDERED_AS_ZERO",
        "NOTIFICATION_DEEP_LINK_DROPPED",
        "PUSH_TOKEN_KIND_MISMATCH",
        "SETTLED_SURFACE_RENDERS_LIVE_PROBABILITY",
        "WINNER_WITH_INCOMPLETE_SCORE",
    }
