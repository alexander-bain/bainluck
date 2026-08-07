from scripts.evals.deadline_parser_boundary_contract import decide, evaluate, load


def _case(case_id):
    return next(case for case in load()["cases"] if case["id"] == case_id)


def test_committed_corpus_matches_oracle():
    result = evaluate(load())
    assert result["total"] == 25
    assert result["passed"] == result["total"], result["cases"]


def test_ordinary_month_prose_never_becomes_a_deadline():
    for case_id in ("trump-may-prose", "march-madness-prose", "seed-number-not-date", "world-cup-month-prose"):
        assert decide(_case(case_id)) == {"verdict": "keep", "reason": "no_authoritative_deadline"}


def test_price_alone_never_decides_expired_rung_lifecycle():
    for case_id in ("threshold-needs-authority", "above-threshold-needs-authority"):
        assert decide(_case(case_id))["verdict"] == "needs_authority"
    assert decide(_case("high-prob-confirmed-answer"))["verdict"] == "keep"


def test_invalid_scales_clocks_and_dates_fail_closed():
    for case_id in ("naive-clock-refusal", "malformed-date", "percent-scale-refusal", "string-probability-refusal"):
        assert decide(_case(case_id))["verdict"] == "refuse"


def test_trace_and_serving_must_share_the_same_disposition():
    assert decide(_case("trace-serving-drift"))["verdict"] == "drifted"
    assert decide(_case("shared-authority-target"))["verdict"] == "shared"
